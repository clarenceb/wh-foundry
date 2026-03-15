/**
 * Audio playback AudioWorklet processor.
 * Receives PCM16 Int16Array buffers from the main thread and plays them.
 * Supports 'flush' message to clear the buffer (used for barge-in).
 */
class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);

    this.port.onmessage = (e) => {
      // 'flush' clears the buffer (barge-in interrupt)
      if (e.data === 'flush') {
        this._buffer = new Float32Array(0);
        return;
      }

      // Convert Int16 → Float32 and append to ring buffer
      const int16 = new Int16Array(e.data);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);
      }

      // Append to buffer
      const newBuf = new Float32Array(this._buffer.length + float32.length);
      newBuf.set(this._buffer);
      newBuf.set(float32, this._buffer.length);
      this._buffer = newBuf;
    };
  }

  process(_inputs, outputs) {
    const output = outputs[0][0]; // mono output
    if (!output) return true;

    const available = Math.min(output.length, this._buffer.length);

    if (available > 0) {
      output.set(this._buffer.subarray(0, available));
      this._buffer = this._buffer.slice(available);
    }

    // Fill remainder with silence
    for (let i = available; i < output.length; i++) {
      output[i] = 0;
    }

    return true;
  }
}

registerProcessor('playback-processor', PlaybackProcessor);
