/**
 * AudioWorkletProcessor for gapless, low-latency PCM playback.
 *
 * Audio contract (matches Sarvam TTS bulbul:v3 output):
 *   - Format  : Int16 PCM (little-endian)
 *   - Rate    : 24000 Hz (bulbul:v3 default; falls back gracefully at 16000)
 *   - Channels: 1 (mono)
 *
 * The server sends binary WebSocket frames of raw Int16 PCM bytes.
 * We decode to Float32, push into a ring buffer, and drain 128 samples per
 * process() call (the AudioWorklet render quantum).
 *
 * Ring buffer capacity: BUFFER_FRAMES * 128 samples.
 * At 24kHz mono:  4800 frames × 128 = 614,400 samples = 25.6 seconds.
 * Sized to hold the ENTIRE TTS audio burst even for long LLM responses.
 * Memory cost: 4800 × 128 × 4 bytes (Float32) ≈ 2.5 MB — safe for browser.
 *
 * Underrun  → silence padding (no crackle).
 * Overrun   → NEWEST data dropped (preserve beginning of speech, not end).
 */

const BUFFER_FRAMES = 4800;        // 25.6 s @ 24kHz — covers even long LLM responses
const RENDER_QUANTUM = 128;        // AudioWorklet fixed quantum

class PCMPlayerProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super(options);

        // Ring buffer: Float32 samples
        this._bufferSize = BUFFER_FRAMES * RENDER_QUANTUM;
        this._buffer = new Float32Array(this._bufferSize);
        this._writeHead = 0;
        this._readHead  = 0;
        this._count     = 0;        // filled samples

        // Receive Int16 PCM chunks from the main thread
        this.port.onmessage = (e) => {
            if (e.data instanceof ArrayBuffer) {
                this._enqueue(e.data);
            } else if (e.data && e.data.type === 'flush') {
                this._writeHead = 0;
                this._readHead  = 0;
                this._count     = 0;
            }
        };
    }

    _enqueue(buffer) {
        const int16 = new Int16Array(buffer);
        for (let i = 0; i < int16.length; i++) {
            if (this._count >= this._bufferSize) {
                // Overrun: drop NEWEST sample (keep existing audio intact so
                // speech plays from the beginning, not from the end).
                // With BUFFER_FRAMES=1200 this should never trigger for normal TTS.
                continue;
            }

            this._buffer[this._writeHead] = int16[i] / 32768.0;  // normalise to [-1, 1]
            this._writeHead = (this._writeHead + 1) % this._bufferSize;
            this._count++;
        }
    }

    process(_inputs, outputs) {
        const channel = outputs[0][0];   // first output, first channel
        const hadSamples = this._count > 0;

        for (let i = 0; i < channel.length; i++) {
            if (this._count > 0) {
                channel[i] = this._buffer[this._readHead];
                this._readHead = (this._readHead + 1) % this._bufferSize;
                this._count--;
            } else {
                channel[i] = 0;          // underrun → silence
            }
        }

        // Immediate notification the moment the last sample plays out.
        // This fires within one 128-sample render quantum (~5 ms at 24 kHz)
        // of the buffer reaching zero — far more accurate than the 2-second
        // periodic report below.
        if (hadSamples && this._count === 0) {
            this.port.postMessage({
                type: 'bufferLevel',
                count: 0,
                capacity: this._bufferSize,
                pct: 0
            });
        }

        // Periodic ~2-second report for capacity-warning UI updates
        if (this._reportTick === undefined) this._reportTick = 0;
        if (++this._reportTick % 375 === 0) {
            this.port.postMessage({
                type: 'bufferLevel',
                count: this._count,
                capacity: this._bufferSize,
                pct: Math.round(this._count / this._bufferSize * 100)
            });
        }

        return true;   // keep processor alive
    }
}

registerProcessor('pcm-player-processor', PCMPlayerProcessor);
