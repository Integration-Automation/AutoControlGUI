// AudioWorklet processor: convert browser Float32 mic samples to int16 PCM
// at 16 kHz mono, posting raw ArrayBuffer chunks back to the main thread.
// The AudioContext is created with sampleRate: 16000 so we don't resample
// here — Float32 → Int16 is the only conversion needed.
class PcmProcessor extends AudioWorkletProcessor {
  // NOSONAR javascript:S3516 — AudioWorkletProcessor.process MUST return
  // true to keep the node alive; returning false would silently kill
  // the mic stream. Both branches are deliberately the same value.
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const samples = input[0];  // Float32Array, [-1, 1]
    const int16 = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      // i is a numeric loop counter, never user input; the "object
      // injection" warning here is a false positive — TypedArrays are
      // not subject to the prototype-pollution class of bug the rule
      // is meant to catch.
      const s = Math.max(-1, Math.min(1, samples[i]));  // NOSONAR
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;       // NOSONAR
    }
    this.port.postMessage(int16.buffer, [int16.buffer]);
    return true;
  }
}
registerProcessor('mic-pcm-processor', PcmProcessor);
