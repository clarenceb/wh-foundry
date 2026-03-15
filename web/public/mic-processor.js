/**
 * Mic capture AudioWorklet processor.
 * Captures raw audio from the microphone and converts to PCM16 Int16Array.
 * Posts Int16Array buffers to the main thread for WebSocket transmission.
 */
class MicProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input.length > 0 && input[0].length > 0) {
      const float32 = input[0]; // mono channel
      const int16 = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {
        const s = Math.max(-1, Math.min(1, float32[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }
    return true;
  }
}

registerProcessor('mic-processor', MicProcessor);
