import { pipeline, env } from '@xenova/transformers';

env.allowLocalModels = false;
env.useBrowserCache = true;

class PipelineFactory {
  static instances = {};

  static async getInstance(task, modelId, logCallback, progressCallback) {
    if (!this.instances[modelId]) {
      logCallback(`Iniciando pipeline para modelo: ${modelId}`);
      this.instances[modelId] = pipeline(task, modelId, {
        progress_callback: progressCallback,
        quantized: true,
      });
    } else {
      logCallback(`Modelo ${modelId} ya estaba cargado en memoria.`);
    }
    return this.instances[modelId];
  }
}

self.addEventListener('message', async (event) => {
  const { text, voiceId } = event.data;
  
  const log = (msg) => self.postMessage({ status: 'log', message: msg });
  log(`Recibida petición de síntesis. Texto: "${text.substring(0, 20)}...", Modo: ${voiceId}`);

  try {
    self.postMessage({ status: 'loading' });

    let audioResult;
    let sampleRate;

    const onProgress = (progress) => {
      self.postMessage({ status: 'progress', data: progress });
    };

    if (voiceId.startsWith('clone_')) {
      log("Modo CLONACIÓN (Predefinida) activado. Utilizando motor SpeechT5.");
      
      const cloneMap = {
        'clone_f1': 'cmu_us_slt_arctic-wav-arctic_a0001.bin',
        'clone_f2': 'cmu_us_clb_arctic-wav-arctic_a0001.bin',
        'clone_m1': 'cmu_us_aew_arctic-wav-arctic_a0001.bin',
        'clone_m2': 'cmu_us_bdl_arctic-wav-arctic_a0001.bin'
      };
      
      const binFile = cloneMap[voiceId] || cloneMap['clone_f1'];
      const speaker_embeddings_url = `https://huggingface.co/datasets/Xenova/cmu-arctic-xvectors-extracted/resolve/main/${binFile}`;
      
      log(`Descargando vector de huella vocal pre-extraído para este perfil...`);
      
      log("Cargando modelo generador de voz (Xenova/speecht5_tts)... Puede tardar 1-3 minutos la primera vez.");
      const synthesizer = await PipelineFactory.getInstance('text-to-speech', 'Xenova/speecht5_tts', log, onProgress);

      log("Generando audio sintetizado con la voz clonada...");
      self.postMessage({ status: 'generating' });
      const result = await synthesizer(text, { speaker_embeddings: speaker_embeddings_url });
      
      audioResult = result.audio;
      sampleRate = result.sampling_rate;
    } else {
      // MMS Native
      const modelId = voiceId === 'spa' ? 'Xenova/mms-tts-spa' : 'Xenova/mms-tts-eng';
      log(`Modo NATIVO seleccionado. Usando MMS VITS: ${modelId}`);
      log("Cargando modelo TTS VITS... Puede tardar 1-3 minutos la primera vez.");
      const synthesizer = await PipelineFactory.getInstance('text-to-speech', modelId, log, onProgress);

      log("Generando audio sintetizado nativemente en WebGPU...");
      self.postMessage({ status: 'generating' });
      const result = await synthesizer(text);
      
      audioResult = result.audio;
      sampleRate = result.sampling_rate;
    }
    
    log("Inferencia completada. Codificando WAV...");
    const wavBlob = encodeWAV(audioResult, sampleRate);
    const audioUrl = URL.createObjectURL(wavBlob);
    
    log("Proceso terminado exitosamente.");
    self.postMessage({ status: 'complete', audio: audioUrl });

  } catch (error) {
    console.error("Worker TTS Error:", error);
    log(`ERROR CRÍTICO: ${error.message}`);
    self.postMessage({ status: 'error', error: error.message });
  }
});

function encodeWAV(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');

  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);

  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([view], { type: 'audio/wav' });
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}
