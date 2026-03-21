# WebGPU-Accelerated Local TTS Implementation Plan

> [!NOTE]
> Plan estrategico actualizado (modo dual + motor local instalable): ver `plan_modo_pro_local.md`.

## Goal Description
The objective is to create a free, open-source clone of ElevenLabs deployed on Railway. Crucially, the application must perform the Text-to-Speech (TTS) computations directly on the user's computer (client-side) via the web browser. This eliminates server costs and ensures maximum privacy, leveraging the user's local hardware resources.

## User Review Required
> [!WARNING]
> You mentioned "Chatterbox TTS" initially. Chatterbox TTS is a powerful model, but to run TTS *entirely in the user's browser* (client-side computation, which is your main goal to make it free), we need models optimized for the Web (ONNX format) that run via WebAssembly/WebGPU. 
> 
> Currently, the most robust way to achieve high-quality, completely in-browser TTS is using **Transformers.js** with models like `Xenova/speecht5_tts` (or newer WebGPU-compatible models). These models perfectly fulfill your core requirement of using the user's hardware for computation without installing anything.
> 
> **Are you okay with using Transformers.js + SpeechT5/VITS instead of specifically Chatterbox TTS to achieve the client-side, free execution goal?** If we strictly use Chatterbox, we would have to deploy it on a server with GPUs, which violates your goal of using the *usuario's recursos del ordenador*.

## Proposed Changes

### Frontend Infrastructure (Vite + React)
We will build a sleek, performant Single Page Application (SPA).
*   **Init Script:** `npx create-vite@latest ./ --template react-ts`
*   **Styling:** Modern Vanilla CSS inspired by ElevenLabs (dark mode, glassmorphism, fluid typography).

### Web Worker & TTS Engine
*   **`src/worker.js` (NEW)**: We will create a Web Worker to handle the TTS inference off the main thread so the UI does not freeze.
*   **Transformers.js Integration**: The worker will load the ONNX model (e.g., `Xenova/speecht5_tts`) and a speaker embedding depending on the selected voice.
*   **Hardware Acceleration**: We will configure Transformers.js to use WebGPU if available, falling back to WebAssembly for older devices.

### UI Components
*   **`src/App.tsx` (MODIFY)**: Main layout with a clean text area, voice selector dropdown, and a "Generate" button.
*   **`src/components/AudioPlayer.tsx` (NEW)**: A custom audio player to handle playback and download of generated audio.
*   **`src/index.css` (MODIFY)**: Implementation of the dark, premium design tokens.

### Deployment Setup (Railway)
*   Since the app is purely client-side, Railway only needs to serve static files. 
*   We can add a basic `package.json` build script or a minimal Node/Express server to serve the `dist/` folder, which Railway will pick up automatically.

## Verification Plan

### Automated Tests
*   **Build Verification**: Run `npm run build` to ensure the static assets compile successfully without TypeScript or Lint errors.

### Manual Verification
1.  **Local Dev Server**: Run `npm run dev` and open the app in a local browser (Chrome/Edge with WebGPU enabled).
2.  **Model Loading Test**: Verify that opening the page begins downloading the model weights into the browser cache.
3.  **Generation Test**: Input text, select a voice, and press 'Generate'. Verify that the Web Worker processes the text and outputs an audio blob.
4.  **Hardware Utilization Test**: Check the browser's Task Manager to ensure the GPU/CPU is being utilized during the text-to-speech generation phase, confirming that the processing is happening client-side.
