// AudioCapture - macOS system audio capture via ScreenCaptureKit SCStream
//
// Captures all system audio and writes raw PCM samples to stdout:
//   16-bit signed integer, 16 kHz, mono, little-endian
//
// Usage:
//   .build/release/AudioCapture | python my_asr_pipeline.py
//   .build/release/AudioCapture > recording.raw
//
// Requires: macOS 13+ (Ventura), Screen & System Audio Recording permission
//           (System Settings > Privacy & Security > Screen & System Audio Recording)
//
// Build:
//   cd audio-capture && swift build -c release

import AVFoundation
import CoreGraphics
import Foundation
import ScreenCaptureKit

// ---------------------------------------------------------------------------
// MARK: - Constants
// ---------------------------------------------------------------------------

/// Target output sample rate (what Whisper / our ASR expects)
let kTargetSampleRate: Double = 16_000

/// Target channel count (mono)
let kTargetChannels: AVAudioChannelCount = 1

// ---------------------------------------------------------------------------
// MARK: - Stderr logging helper
// ---------------------------------------------------------------------------

func log(_ message: String) {
    var stderr = FileHandle.standardError
    print(message, to: &stderr)
}

extension FileHandle: @retroactive TextOutputStream {
    public func write(_ string: String) {
        if let data = string.data(using: .utf8) {
            self.write(data)
        }
    }
}

// ---------------------------------------------------------------------------
// MARK: - SCStreamRecorder
// ---------------------------------------------------------------------------

/// Captures system audio via SCStream (ScreenCaptureKit), converts to
/// 16 kHz Int16 mono, and writes raw bytes to stdout.
final class SCStreamRecorder: NSObject, SCStreamDelegate, SCStreamOutput {

    private var stream: SCStream?

    // Lazy converter — initialized from first callback's actual ASBD
    private var converter: AVAudioConverter?
    private var outputFormat: AVAudioFormat?
    private var converterInitLock = NSLock()

    // Diagnostics
    private var callbackCount: Int64 = 0
    private var emptyCallbackCount: Int64 = 0
    private var bytesWritten: Int64 = 0
    private var diagTimer: DispatchSourceTimer?

    // ---------------------------------------------------------------------------
    // Start
    // ---------------------------------------------------------------------------

    func start() async throws {
        // Permission checks can be stale after app/binary updates on some systems.
        // If preflight says "not granted", request access once before giving up.
        if !CGPreflightScreenCaptureAccess() {
            log("[AudioCapture] Screen Recording preflight is false; requesting access...")
            let granted = CGRequestScreenCaptureAccess()
            if !granted {
                log("[AudioCapture] ERROR: Screen Recording permission not granted.")
                log("[AudioCapture] Open System Settings > Privacy & Security > Screen & System Audio Recording and enable Meeting Buddy (or Terminal/iTerm when running from the command line).")
                exit(1)
            }
            log("[AudioCapture] Screen Recording access granted by request API.")
        }

        log("[AudioCapture] requesting shareable content...")
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)

        guard let display = content.displays.first else {
            log("[AudioCapture] ERROR: no display found")
            throw NSError(domain: "AudioCapture", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "No display available"])
        }

        let filter = SCContentFilter(display: display,
                                     excludingApplications: [],
                                     exceptingWindows: [])

        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = false
        config.sampleRate = 48000
        config.channelCount = 2

        // Minimal video required — SCKit's internal pipeline won't init without it
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)  // 1 fps
        config.showsCursor = false

        let stream = SCStream(filter: filter, configuration: config, delegate: self)

        // Video output required even as no-op (SCKit internal requirement)
        try stream.addStreamOutput(self,
                                   type: .screen,
                                   sampleHandlerQueue: DispatchQueue(label: "sc.video.drop"))
        try stream.addStreamOutput(self,
                                   type: .audio,
                                   sampleHandlerQueue: DispatchQueue(label: "sc.audio",
                                                                     qos: .userInteractive))

        try await stream.startCapture()
        self.stream = stream

        log("[AudioCapture] capturing system audio -> stdout (16-bit signed LE, 16 kHz, mono)")
        log("[AudioCapture] press Ctrl+C to stop")

        // Periodic diagnostic every 5 seconds
        let diagTimer = DispatchSource.makeTimerSource(queue: .main)
        diagTimer.schedule(deadline: .now() + 5, repeating: 5.0)
        diagTimer.setEventHandler { [weak self] in
            guard let self = self else { return }
            let cb    = OSAtomicAdd64(0, &self.callbackCount)
            let empty = OSAtomicAdd64(0, &self.emptyCallbackCount)
            let bytes = OSAtomicAdd64(0, &self.bytesWritten)
            log("[AudioCapture] diag: callbacks=\(cb), empty=\(empty), bytesWritten=\(bytes)")
        }
        diagTimer.resume()
        self.diagTimer = diagTimer
    }

    func stop() {
        diagTimer?.cancel()
        diagTimer = nil
        log("[AudioCapture] shutting down...")
        Task { try? await stream?.stopCapture() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { exit(0) }
    }

    // ---------------------------------------------------------------------------
    // SCStreamOutput delegate
    // ---------------------------------------------------------------------------

    func stream(_ stream: SCStream,
                didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of outputType: SCStreamOutputType) {

        // Silently discard video frames
        guard outputType == .audio else { return }

        OSAtomicIncrement64(&callbackCount)

        guard CMSampleBufferDataIsReady(sampleBuffer) else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }

        // Get source format from this buffer
        guard let fmtDesc = CMSampleBufferGetFormatDescription(sampleBuffer),
              let asbdPtr = CMAudioFormatDescriptionGetStreamBasicDescription(fmtDesc) else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }
        let asbd = asbdPtr.pointee

        // Lazy-init converter from the first real callback's ASBD
        converterInitLock.lock()
        if converter == nil {
            initConverter(asbd: asbd)
        }
        converterInitLock.unlock()

        guard let converter = self.converter, let outFmt = self.outputFormat else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }

        // Extract audio buffer list — two-call pattern required.
        // AudioBufferList as a Swift stack var only has room for 1 AudioBuffer entry,
        // but non-interleaved multichannel audio requires N entries.
        // We must allocate exactly bufferListSize bytes dynamically.
        var bufferListSize: Int = 0
        var blockBuffer: CMBlockBuffer?

        // First call: get required size
        CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: &bufferListSize,
            bufferListOut: nil,
            bufferListSize: 0,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: nil
        )

        guard bufferListSize > 0 else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }

        // Allocate exactly the required bytes so all AudioBuffer entries fit
        let ablMem = UnsafeMutableRawPointer.allocate(
            byteCount: bufferListSize,
            alignment: MemoryLayout<AudioBufferList>.alignment
        )
        defer { ablMem.deallocate() }
        let ablPtr = ablMem.bindMemory(to: AudioBufferList.self, capacity: 1)

        // Second call: get the actual data
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: ablPtr,
            bufferListSize: bufferListSize,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: &blockBuffer
        )

        guard status == noErr else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }

        // blockBuffer is +1 retained — ARC releases when it goes out of scope

        // Build source AVAudioFormat from the exact callback ASBD.
        // Do not force Float32: some systems provide different PCM layouts.
        var mutableASBD = asbd
        guard let srcFmt = AVAudioFormat(streamDescription: &mutableASBD) else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }

        let frameCount = AVAudioFrameCount(CMSampleBufferGetNumSamples(sampleBuffer))
        guard frameCount > 0 else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }

        // Wrap audio buffer list in AVAudioPCMBuffer (no copy)
        guard let srcBuffer = AVAudioPCMBuffer(
            pcmFormat: srcFmt,
            bufferListNoCopy: ablPtr,
            deallocator: nil
        ) else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }
        srcBuffer.frameLength = frameCount

        // Calculate output capacity and allocate output buffer
        let ratio = outFmt.sampleRate / srcFmt.sampleRate
        let outCapacity = AVAudioFrameCount(ceil(Double(frameCount) * ratio))
        guard let outBuffer = AVAudioPCMBuffer(pcmFormat: outFmt, frameCapacity: outCapacity) else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }

        // Convert (resample + format change)
        var convError: NSError?
        var hasData = true
        let convStatus = converter.convert(to: outBuffer, error: &convError) { _, outStatus in
            if hasData {
                hasData = false
                outStatus.pointee = .haveData
                return srcBuffer
            } else {
                outStatus.pointee = .noDataNow
                return nil
            }
        }

        guard convStatus != .error, outBuffer.frameLength > 0 else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }

        // Write Int16 samples to stdout
        guard let int16Ptr = outBuffer.int16ChannelData?[0] else {
            OSAtomicIncrement64(&emptyCallbackCount)
            return
        }
        let byteCount = Int(outBuffer.frameLength)
            * Int(outFmt.streamDescription.pointee.mBytesPerFrame)
        let rawData = Data(bytes: int16Ptr, count: byteCount)
        FileHandle.standardOutput.write(rawData)
        OSAtomicIncrement64(&bytesWritten)
    }

    // ---------------------------------------------------------------------------
    // SCStreamDelegate
    // ---------------------------------------------------------------------------

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        log("[AudioCapture] stream stopped with error: \(error)")
        exit(1)
    }

    // ---------------------------------------------------------------------------
    // Private: lazy converter init
    // ---------------------------------------------------------------------------

    private func initConverter(asbd: AudioStreamBasicDescription) {
        var mutableASBD = asbd
        guard let srcFmt = AVAudioFormat(streamDescription: &mutableASBD) else {
            log("[AudioCapture] ERROR: failed to create source AVAudioFormat")
            return
        }
        log(
            "[AudioCapture] source format: \(srcFmt.sampleRate) Hz, \(srcFmt.channelCount) ch, "
            + "commonFormat=\(srcFmt.commonFormat.rawValue), interleaved=\(srcFmt.isInterleaved), "
            + "formatFlags=0x\(String(mutableASBD.mFormatFlags, radix: 16))"
        )

        guard let tgtFmt = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: kTargetSampleRate,
            channels: kTargetChannels,
            interleaved: true
        ) else {
            log("[AudioCapture] ERROR: failed to create target AVAudioFormat")
            return
        }

        guard let conv = AVAudioConverter(from: srcFmt, to: tgtFmt) else {
            log("[AudioCapture] ERROR: failed to create AVAudioConverter")
            return
        }

        self.converter = conv
        self.outputFormat = tgtFmt

        log("[AudioCapture] converter ready: "
            + "\(srcFmt.sampleRate) Hz \(srcFmt.channelCount)ch \(srcFmt.commonFormat.rawValue) "
            + "-> \(tgtFmt.sampleRate) Hz \(tgtFmt.channelCount)ch Int16")
    }
}

// ---------------------------------------------------------------------------
// MARK: - Entry point
// ---------------------------------------------------------------------------

let recorder = SCStreamRecorder()

// Set up signal handlers for graceful shutdown
let sigintSource  = DispatchSource.makeSignalSource(signal: SIGINT,  queue: .main)
let sigtermSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)

signal(SIGINT,  SIG_IGN)
signal(SIGTERM, SIG_IGN)

let shutdown = {
    recorder.stop()
}

sigintSource.setEventHandler(handler: shutdown)
sigtermSource.setEventHandler(handler: shutdown)
sigintSource.resume()
sigtermSource.resume()

// Start capture (async — needs MainActor for SCShareableContent)
Task { @MainActor in
    do {
        try await recorder.start()
    } catch {
        log("[AudioCapture] FATAL: \(error)")
        exit(1)
    }
}

// Keep alive — audio callbacks run on their own thread
dispatchMain()
