// AudioWorklet processor: convert browser Float32 mic samples to int16 PCM
// at 16 kHz mono, posting raw ArrayBuffer chunks back to the main thread.
// The AudioContext is created with sampleRate: 16000 so we don't resample
// here — Float32 → Int16 is the only conversion needed.
class PcmProcessor extends AudioWorkletProcessor {
  // AudioWorkletProcessor.process MUST return true to keep the node
  // alive; returning false would silently kill the mic stream. Single
  // exit point keeps Sonar's S3516 happy without an exception marker.
  process(inputs) {
    const samples = inputs[0]?.[0];  // optional chain (S6582)
    if (samples) {
      const int16 = new Int16Array(samples.length);
      // nosemgrep: javascript.lang.security.audit.detect-object-injection
      // ``i`` is a numeric loop counter from 0..length-1 driving the
      // Float32Array / Int16Array typed-array element access. TypedArrays
      // clamp out-of-range indices and do not honour the prototype chain,
      // so the prototype-pollution class of bug that
      // ``security/detect-object-injection`` is built to find cannot
      // apply here — there is no user-controlled key path involved.
      for (let i = 0; i < samples.length; i++) {
        // eslint-disable-next-line security/detect-object-injection
        const s = Math.max(-1, Math.min(1, samples[i]));
        // eslint-disable-next-line security/detect-object-injection
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }
    return true;
  }
}
registerProcessor('mic-pcm-processor', PcmProcessor);
