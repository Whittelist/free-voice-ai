import { env, pipeline } from "@huggingface/transformers";

env.allowLocalModels = false;
env.useBrowserCache = true;

const supportsWebGPU = typeof navigator !== "undefined" && "gpu" in navigator;

class PipelineFactory {
  static instances = {};

  static async getInstance(task, modelId, logCallback, progressCallback) {
    if (this.instances[modelId]) {
      logCallback(`Modelo ${modelId} ya estaba cargado en memoria.`);
      return this.instances[modelId];
    }

    logCallback(`Iniciando pipeline para modelo: ${modelId}`);

    const baseOptions = {
      progress_callback: progressCallback,
      dtype: supportsWebGPU ? "fp32" : "q8",
    };

    const firstAttemptOptions = supportsWebGPU
      ? {
          ...baseOptions,
          device: "webgpu",
        }
      : baseOptions;

    try {
      this.instances[modelId] = await pipeline(task, modelId, firstAttemptOptions);
      return this.instances[modelId];
    } catch (error) {
      if (supportsWebGPU) {
        logCallback("WebGPU no disponible para este modelo. Reintentando en CPU/WASM...");
        this.instances[modelId] = await pipeline(task, modelId, {
          progress_callback: progressCallback,
          dtype: "q8",
        });
        return this.instances[modelId];
      }
      throw error;
    }
  }
}

self.addEventListener("message", async (event) => {
  const { text, voiceId } = event.data;

  const log = (msg) => self.postMessage({ status: "log", message: msg });
  log(`Recibida peticion de sintesis. Texto: "${text.substring(0, 20)}...", Modo: ${voiceId}`);

  try {
    self.postMessage({ status: "loading" });

    let audioResult;
    let sampleRate;

    const onProgress = (progress) => {
      self.postMessage({ status: "progress", data: progress });
    };

    if (voiceId.startsWith("clone_")) {
      log("Modo CLONACION (predefinida) activado. Usando SpeechT5.");

      const cloneMap = {
        clone_f1: "cmu_us_slt_arctic-wav-arctic_a0001.bin",
        clone_f2: "cmu_us_clb_arctic-wav-arctic_a0001.bin",
        clone_m1: "cmu_us_aew_arctic-wav-arctic_a0001.bin",
        clone_m2: "cmu_us_bdl_arctic-wav-arctic_a0001.bin",
      };

      const binFile = cloneMap[voiceId] || cloneMap.clone_f1;
      const speakerEmbeddingsUrl = `https://huggingface.co/datasets/Xenova/cmu-arctic-xvectors-extracted/resolve/main/${binFile}`;

      log("Cargando modelo SpeechT5... La primera vez puede tardar 1-3 minutos.");
      const synthesizer = await PipelineFactory.getInstance("text-to-speech", "Xenova/speecht5_tts", log, onProgress);

      log("Generando audio sintetizado...");
      self.postMessage({ status: "generating" });
      const result = await synthesizer(text, { speaker_embeddings: speakerEmbeddingsUrl });

      audioResult = result.audio;
      sampleRate = result.sampling_rate;
    } else {
      const modelId = voiceId === "spa" ? "Xenova/mms-tts-spa" : "Xenova/mms-tts-eng";
      log(`Modo nativo seleccionado. Usando MMS VITS: ${modelId}`);
      log("Cargando modelo MMS TTS... La primera vez puede tardar 1-3 minutos.");
      const synthesizer = await PipelineFactory.getInstance("text-to-speech", modelId, log, onProgress);

      log("Generando audio en navegador...");
      self.postMessage({ status: "generating" });
      const result = await synthesizer(text);

      audioResult = result.audio;
      sampleRate = result.sampling_rate;
    }

    log("Inferencia completada. Codificando WAV...");
    const wavBlob = encodeWAV(audioResult, sampleRate);
    const audioUrl = URL.createObjectURL(wavBlob);

    log("Proceso terminado correctamente.");
    self.postMessage({ status: "complete", audio: audioUrl });
  } catch (error) {
    console.error("Worker TTS Error:", error);
    const message = error instanceof Error ? error.message : String(error);
    log(`ERROR CRITICO: ${message}`);
    self.postMessage({ status: "error", error: message });
  }
});

function encodeWAV(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, "WAVE");

  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);

  writeString(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([view], { type: "audio/wav" });
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i += 1) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}
