// AudioCapture - macOS system audio capture via Core Audio Taps
//
// Captures all system audio (no video, no screen sharing indicator) and writes
// raw PCM samples to stdout:
//   16-bit signed integer, 16 kHz, mono, little-endian
//
// Usage:
//   .build/release/AudioCapture | python my_asr_pipeline.py
//   .build/release/AudioCapture > recording.raw
//
// Requires: macOS 14.2+ (Sonoma), System Audio Recording permission
//           (System Settings > Privacy & Security > Screen & System Audio Recording
//            → scroll to "System Audio Recording Only" section)
//
// Build:
//   cd audio-capture && swift build -c release

import AVFoundation
import AudioToolbox
import CoreAudio
import Foundation

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
// MARK: - Helper: AudioObjectPropertyAddress
// ---------------------------------------------------------------------------

func propertyAddress(selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
        mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
}

// ---------------------------------------------------------------------------
// MARK: - AudioTapRecorder
// ---------------------------------------------------------------------------

/// Creates a Core Audio Tap on all system audio, reads samples via an IO proc
/// callback, converts to 16 kHz Int16 mono, and writes raw bytes to stdout.
final class AudioTapRecorder {

    private var tapID: AudioObjectID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateDeviceID: AudioObjectID = 0
    private var ioProcID: AudioDeviceIOProcID?

    // Audio format conversion
    private var converter: AVAudioConverter?
    private var outputFormat: AVAudioFormat?
    private var sourceFormat: AVAudioFormat?

    // ---------------------------------------------------------------------------
    // Setup
    // ---------------------------------------------------------------------------

    func start() throws {
        // 1. Create a system-wide audio tap
        try createTap()

        // 2. Create an aggregate device to host the tap
        try createAggregateDevice()

        // 3. Attach the tap to the aggregate device
        try attachTapToDevice()

        // 4. Read the device's source format and set up conversion
        try setupConverter()

        // 5. Start the IO proc (audio callback)
        try startIOProc()

        log("[AudioCapture] capturing system audio -> stdout "
            + "(16-bit signed LE, 16 kHz, mono)")
        log("[AudioCapture] press Ctrl+C to stop")
    }

    func stop() {
        log("[AudioCapture] shutting down...")

        if let ioProcID = ioProcID {
            AudioDeviceStop(aggregateDeviceID, ioProcID)
            AudioDeviceDestroyIOProcID(aggregateDeviceID, ioProcID)
            self.ioProcID = nil
        }
        if tapID != AudioObjectID(kAudioObjectUnknown) {
            AudioHardwareDestroyProcessTap(tapID)
            tapID = AudioObjectID(kAudioObjectUnknown)
        }
        if aggregateDeviceID != 0 {
            AudioHardwareDestroyAggregateDevice(aggregateDeviceID)
            aggregateDeviceID = 0
        }

        log("[AudioCapture] capture stopped cleanly")
    }

    // ---------------------------------------------------------------------------
    // 1. Create the tap
    // ---------------------------------------------------------------------------

    private func createTap() throws {
        log("[AudioCapture] creating system audio tap...")

        let description = CATapDescription()
        description.name = "meeting-buddy-tap"
        // No processes → captures ALL system audio
        description.isPrivate = true
        description.isMixdown = true
        description.isMono = false     // get stereo from system, we'll mix to mono ourselves
        description.isExclusive = false
        description.muteBehavior = .unmuted

        var newTapID = AudioObjectID(kAudioObjectUnknown)
        let status = AudioHardwareCreateProcessTap(description, &newTapID)

        guard status == kAudioHardwareNoError else {
            log("[AudioCapture] ERROR: AudioHardwareCreateProcessTap failed: \(status)")
            throw NSError(domain: "AudioCapture", code: Int(status))
        }

        tapID = newTapID
        log("[AudioCapture] tap created (ID: \(tapID))")
    }

    // ---------------------------------------------------------------------------
    // 2. Create aggregate device
    // ---------------------------------------------------------------------------

    private func createAggregateDevice() throws {
        let uid = UUID().uuidString
        let description: [String: Any] = [
            kAudioAggregateDeviceNameKey: "meeting-buddy-aggregate",
            kAudioAggregateDeviceUIDKey: uid,
            kAudioAggregateDeviceSubDeviceListKey: [] as CFArray,
            kAudioAggregateDeviceMasterSubDeviceKey: 0,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
        ]

        var deviceID: AudioObjectID = 0
        let status = AudioHardwareCreateAggregateDevice(description as CFDictionary, &deviceID)

        guard status == kAudioHardwareNoError else {
            log("[AudioCapture] ERROR: AudioHardwareCreateAggregateDevice failed: \(status)")
            throw NSError(domain: "AudioCapture", code: Int(status))
        }

        aggregateDeviceID = deviceID
        log("[AudioCapture] aggregate device created (ID: \(aggregateDeviceID))")
    }

    // ---------------------------------------------------------------------------
    // 3. Attach tap to device
    // ---------------------------------------------------------------------------

    private func attachTapToDevice() throws {
        // Get the tap's UID
        var addr = propertyAddress(selector: kAudioTapPropertyUID)
        var size = UInt32(MemoryLayout<CFString>.stride)
        var tapUID: CFString = "" as CFString

        withUnsafeMutablePointer(to: &tapUID) { ptr in
            _ = AudioObjectGetPropertyData(tapID, &addr, 0, nil, &size, ptr)
        }

        // Add the tap to the aggregate device's tap list
        addr = propertyAddress(selector: kAudioAggregateDevicePropertyTapList)
        let tapArray = [tapUID] as CFArray
        size = UInt32(MemoryLayout<CFArray>.stride)

        let status = withUnsafePointer(to: tapArray) { ptr in
            AudioObjectSetPropertyData(aggregateDeviceID, &addr, 0, nil, size, ptr)
        }

        guard status == kAudioHardwareNoError else {
            log("[AudioCapture] ERROR: failed to attach tap to device: \(status)")
            throw NSError(domain: "AudioCapture", code: Int(status))
        }

        log("[AudioCapture] tap attached to aggregate device")
    }

    // ---------------------------------------------------------------------------
    // 4. Set up format converter
    // ---------------------------------------------------------------------------

    private func setupConverter() throws {
        // Read the device's input format
        var addr = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamFormat,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.stride)
        var asbd = AudioStreamBasicDescription()

        let status = AudioObjectGetPropertyData(
            aggregateDeviceID, &addr, 0, nil, &size, &asbd
        )

        guard status == kAudioHardwareNoError else {
            log("[AudioCapture] ERROR: couldn't read device format: \(status)")
            throw NSError(domain: "AudioCapture", code: Int(status))
        }

        log("[AudioCapture] source format: "
            + "\(asbd.mSampleRate) Hz, "
            + "\(asbd.mChannelsPerFrame) ch, "
            + "\(asbd.mBitsPerChannel) bit")

        // Source format: Float32, non-interleaved (typical for Core Audio)
        guard let srcFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: asbd.mSampleRate,
            channels: asbd.mChannelsPerFrame,
            interleaved: false
        ) else {
            log("[AudioCapture] ERROR: failed to create source AVAudioFormat")
            throw NSError(domain: "AudioCapture", code: -1)
        }

        // Target format: Int16, 16 kHz, mono, interleaved
        guard let tgtFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: kTargetSampleRate,
            channels: kTargetChannels,
            interleaved: true
        ) else {
            log("[AudioCapture] ERROR: failed to create target AVAudioFormat")
            throw NSError(domain: "AudioCapture", code: -2)
        }

        guard let conv = AVAudioConverter(from: srcFormat, to: tgtFormat) else {
            log("[AudioCapture] ERROR: failed to create AVAudioConverter")
            throw NSError(domain: "AudioCapture", code: -3)
        }

        self.converter = conv
        self.sourceFormat = srcFormat
        self.outputFormat = tgtFormat

        log("[AudioCapture] converter ready: "
            + "\(srcFormat.sampleRate) Hz \(srcFormat.channelCount)ch Float32 "
            + "-> \(tgtFormat.sampleRate) Hz \(tgtFormat.channelCount)ch Int16")
    }

    // ---------------------------------------------------------------------------
    // 5. Start IO proc
    // ---------------------------------------------------------------------------

    private func startIOProc() throws {
        var procID: AudioDeviceIOProcID?

        let status = AudioDeviceCreateIOProcID(
            aggregateDeviceID,
            { (_, _, inInputData, _, _, _, inClientData) -> OSStatus in
                guard let clientData = inClientData else { return noErr }
                let recorder = Unmanaged<AudioTapRecorder>.fromOpaque(clientData)
                    .takeUnretainedValue()
                recorder.handleAudioCallback(inInputData)
                return noErr
            },
            Unmanaged.passUnretained(self).toOpaque(),
            &procID
        )

        guard status == noErr, let procID = procID else {
            log("[AudioCapture] ERROR: AudioDeviceCreateIOProcID failed: \(status)")
            throw NSError(domain: "AudioCapture", code: Int(status))
        }

        self.ioProcID = procID

        let startStatus = AudioDeviceStart(aggregateDeviceID, procID)
        guard startStatus == noErr else {
            log("[AudioCapture] ERROR: AudioDeviceStart failed: \(startStatus)")
            throw NSError(domain: "AudioCapture", code: Int(startStatus))
        }

        log("[AudioCapture] IO proc started")
    }

    // ---------------------------------------------------------------------------
    // Audio callback (real-time thread)
    // ---------------------------------------------------------------------------

    private func handleAudioCallback(_ inputData: UnsafePointer<AudioBufferList>?) {
        guard let inputData = inputData,
              let converter = self.converter,
              let srcFormat = self.sourceFormat,
              let outFmt = self.outputFormat else {
            return
        }

        let bufferList = inputData.pointee
        let firstBuffer = bufferList.mBuffers

        guard let data = firstBuffer.mData, firstBuffer.mDataByteSize > 0 else {
            return
        }

        // Calculate frame count from the input buffer
        let bytesPerFrame = srcFormat.streamDescription.pointee.mBytesPerFrame
        guard bytesPerFrame > 0 else { return }
        let frameCount = AVAudioFrameCount(firstBuffer.mDataByteSize / bytesPerFrame)
        guard frameCount > 0 else { return }

        // Create source PCM buffer wrapping the input data
        guard let srcBuffer = AVAudioPCMBuffer(
            pcmFormat: srcFormat,
            frameCapacity: frameCount
        ) else { return }
        srcBuffer.frameLength = frameCount

        // Copy channel data
        let channelCount = Int(srcFormat.channelCount)
        if srcFormat.isInterleaved {
            // Interleaved: single buffer, copy directly
            if let dst = srcBuffer.floatChannelData?[0] {
                let bytes = min(
                    Int(firstBuffer.mDataByteSize),
                    Int(frameCount) * MemoryLayout<Float>.size * channelCount
                )
                memcpy(dst, data, bytes)
            }
        } else {
            // Non-interleaved: the IO callback delivers interleaved data in a single buffer.
            // We need to deinterleave into separate channel pointers.
            let floatPtr = data.assumingMemoryBound(to: Float.self)
            let totalSamples = Int(frameCount) * channelCount

            if channelCount > 1 && totalSamples > 0 {
                // Core Audio IO proc typically delivers interleaved Float32
                for ch in 0..<channelCount {
                    guard let dst = srcBuffer.floatChannelData?[ch] else { continue }
                    for frame in 0..<Int(frameCount) {
                        let idx = frame * channelCount + ch
                        if idx < totalSamples {
                            dst[frame] = floatPtr[idx]
                        }
                    }
                }
            } else if let dst = srcBuffer.floatChannelData?[0] {
                let bytes = min(
                    Int(firstBuffer.mDataByteSize),
                    Int(frameCount) * MemoryLayout<Float>.size
                )
                memcpy(dst, data, bytes)
            }
        }

        // Calculate output frame capacity after resampling
        let ratio = outFmt.sampleRate / srcFormat.sampleRate
        let outFrameCapacity = AVAudioFrameCount(ceil(Double(frameCount) * ratio))
        guard let outBuffer = AVAudioPCMBuffer(
            pcmFormat: outFmt,
            frameCapacity: outFrameCapacity
        ) else { return }

        // Perform the conversion (resample + format change)
        var error: NSError?
        var hasData = true
        let convStatus = converter.convert(
            to: outBuffer,
            error: &error
        ) { _, outStatus in
            if hasData {
                hasData = false
                outStatus.pointee = .haveData
                return srcBuffer
            } else {
                outStatus.pointee = .noDataNow
                return nil
            }
        }

        if convStatus == .error {
            return
        }

        guard outBuffer.frameLength > 0 else { return }

        // Write Int16 samples to stdout
        guard let int16Ptr = outBuffer.int16ChannelData?[0] else { return }
        let byteCount = Int(outBuffer.frameLength)
            * Int(outFmt.streamDescription.pointee.mBytesPerFrame)
        let rawData = Data(bytes: int16Ptr, count: byteCount)
        FileHandle.standardOutput.write(rawData)
    }
}

// ---------------------------------------------------------------------------
// MARK: - Entry point
// ---------------------------------------------------------------------------

let recorder = AudioTapRecorder()

// Set up signal handlers for graceful shutdown
let sigintSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
let sigtermSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)

signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)

let shutdown = {
    recorder.stop()
    exit(0)
}

sigintSource.setEventHandler(handler: shutdown)
sigtermSource.setEventHandler(handler: shutdown)
sigintSource.resume()
sigtermSource.resume()

// Start capture
do {
    try recorder.start()
} catch {
    log("[AudioCapture] FATAL: \(error)")
    exit(1)
}

// Keep alive — audio callbacks run on their own thread
dispatchMain()
