import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Cpu,
  Download,
  Loader2,
  Play,
  RefreshCw,
  Server,
  Terminal,
  UploadCloud,
} from "lucide-react";
import {
  type DownloadState,
  type EngineCapabilities,
  type EngineEvent,
  type EngineStatus,
  getLocalNetworkPermissionState,
  LocalEngineError,
  getDefaultLocalEngineUrl,
  localEngineClient,
} from "./localEngineClient";
import "./index.css";

type AppMode = "quick" | "pro";
type QuickVoice = "spa" | "eng" | "clone_f1" | "clone_f2" | "clone_m1" | "clone_m2";
type ProLanguage = "es" | "en";

type Progress = {
  status: string;
  progress?: number;
};

const QUICK_TEXT_ES =
  "Hola, bienvenido al futuro de la sintesis de voz. Este audio se genera localmente en tu navegador.";
const QUICK_TEXT_EN =
  "Welcome to the future of voice synthesis. This audio is generated locally in your browser.";
const QUICK_TEXT_CLONE =
  "Welcome to voice cloning profiles. This quick mode uses precomputed voices for fast generation.";
const PRO_TEXT_ES =
  "Hola, este es el modo Pro local. Puedes clonar una voz real usando un audio de referencia.";
const PRO_TEXT_EN =
  "Hello, this is local Pro mode. You can clone a real voice using a reference audio sample.";

const PRO_ENABLED = import.meta.env.VITE_ENABLE_PRO_MODE !== "false";
const PRO_MODEL_PROFILE = "pro_multilingual_balanced";
const PRO_CFG_WEIGHT_RANGE = { min: 0.0, max: 1.5, step: 0.05 } as const;
const PRO_EXAGGERATION_RANGE = { min: 0.0, max: 2.0, step: 0.05 } as const;
const PRO_TEMPERATURE_RANGE = { min: 0.1, max: 2.0, step: 0.05 } as const;
const PRO_ADVANCED_DEFAULTS = {
  cfgWeight: 0.5,
  exaggeration: 0.5,
  temperature: 0.8,
} as const;
const LOCAL_ENGINE_WINDOWS_INSTALLER_URL =
  (import.meta.env.VITE_LOCAL_ENGINE_WINDOWS_INSTALLER_URL as string | undefined) ??
  "https://github.com/Whittelist/free-voice-ai/releases/latest/download/StudioVoiceLocalEngine.exe";
const PRO_DOWNLOAD_STAGE_LABELS: Record<string, string> = {
  queued: "en cola",
  downloading: "descargando componentes",
  initializing_backend: "inicializando backend real (cache/checkpoints)",
};

function App() {
  const [mode, setMode] = useState<AppMode>("quick");
  const [text, setText] = useState<string>(QUICK_TEXT_ES);
  const [quickVoice, setQuickVoice] = useState<QuickVoice>("spa");
  const [proLanguage, setProLanguage] = useState<ProLanguage>("es");
  const [referenceAudio, setReferenceAudio] = useState<File | null>(null);
  const [proCfgWeight, setProCfgWeight] = useState<number>(PRO_ADVANCED_DEFAULTS.cfgWeight);
  const [proExaggeration, setProExaggeration] = useState<number>(PRO_ADVANCED_DEFAULTS.exaggeration);
  const [proTemperature, setProTemperature] = useState<number>(PRO_ADVANCED_DEFAULTS.temperature);
  const [proSeedInput, setProSeedInput] = useState<string>("");

  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);

  const [engineUrl, setEngineUrl] = useState<string>(getDefaultLocalEngineUrl());
  const [engineToken, setEngineToken] = useState<string>(() => localStorage.getItem("local_engine_token") ?? "");
  const [engineStatus, setEngineStatus] = useState<EngineStatus>("not_installed");
  const [engineNote, setEngineNote] = useState<string>("Motor local no detectado.");
  const [engineCapabilities, setEngineCapabilities] = useState<EngineCapabilities | null>(null);
  const [downloadState, setDownloadState] = useState<DownloadState | null>(null);
  const [isPreparingPro, setIsPreparingPro] = useState(false);
  const lastLoggedDownloadErrorRef = useRef<string | null>(null);
  const lastLoggedDownloadStageRef = useRef<string | null>(null);

  const workerRef = useRef<Worker | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const addLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, `[${timestamp}] ${message}`]);
  }, []);

  const setDefaultQuickText = useCallback((voice: QuickVoice) => {
    if (voice === "spa") setText(QUICK_TEXT_ES);
    else if (voice === "eng") setText(QUICK_TEXT_EN);
    else setText(QUICK_TEXT_CLONE);
  }, []);

  const setDefaultProText = useCallback((language: ProLanguage) => {
    setText(language === "es" ? PRO_TEXT_ES : PRO_TEXT_EN);
  }, []);

  const currentStatusClass = useMemo(() => {
    switch (engineStatus) {
      case "ready":
        return "status-ready";
      case "downloading":
        return "status-downloading";
      case "error":
        return "status-error";
      case "stopped":
        return "status-stopped";
      default:
        return "status-missing";
    }
  }, [engineStatus]);

  const refreshEngineStatus = useCallback(
    async (verbose = false) => {
      if (!PRO_ENABLED) return;
      if (verbose) {
        addLog("Modo Pro: comprobando motor local...");
      }
      try {
        await localEngineClient.health(engineUrl);
      } catch {
        const lnaPermission = await getLocalNetworkPermissionState();
        const insecureRemote =
          typeof window !== "undefined" &&
          !window.isSecureContext &&
          window.location.hostname !== "localhost" &&
          window.location.hostname !== "127.0.0.1";
        const secureRemote =
          typeof window !== "undefined" &&
          window.location.protocol === "https:" &&
          window.location.hostname !== "localhost" &&
          window.location.hostname !== "127.0.0.1";
        const secureHint = insecureRemote
          ? " El dominio no esta en contexto seguro (TLS); corrige el certificado del dominio en Railway."
          : "";
        const lnaHint = secureRemote
          ? " Si usas Chrome/Edge reciente, permite 'Acceso a red local' para este dominio y vuelve a comprobar."
          : "";
        const lnaStateHint =
          lnaPermission !== "unsupported"
            ? ` Estado del permiso local-network-access: ${lnaPermission}.`
            : "";
        setEngineStatus("not_installed");
        setEngineNote(
          `No hay servicio local en localhost. Inicia el motor con .\\local_engine_windows\\run_local_engine.bat.${secureHint}${lnaHint}${lnaStateHint}`,
        );
        setEngineCapabilities(null);
        setDownloadState(null);
        lastLoggedDownloadStageRef.current = null;
        if (verbose) addLog("Modo Pro: motor local no detectado.");
        if (verbose && typeof window !== "undefined") {
          addLog(
            `Diagnostico Pro: origin=${window.location.origin}, secure=${window.isSecureContext}, motor=${engineUrl}`,
          );
        }
        return;
      }

      if (!engineToken.trim()) {
        setEngineStatus("stopped");
        setEngineNote("Motor detectado. Falta token local para operar.");
        setEngineCapabilities(null);
        if (verbose) addLog("Modo Pro: motor detectado, introduce token local.");
        return;
      }

      try {
        const [capabilities, download] = await Promise.all([
          localEngineClient.capabilities(engineUrl, engineToken),
          localEngineClient.downloadStatus(engineUrl, engineToken, PRO_MODEL_PROFILE),
        ]);

        setEngineCapabilities(capabilities);
        setDownloadState(download);

        if (capabilities.inference_backend === "mock") {
          setEngineStatus("error");
          const detail = capabilities.real_backend_error
            ? ` Motivo: ${capabilities.real_backend_error}`
            : "";
          setEngineNote(
            `Motor local detectado, pero en modo mock (sin clonacion real). Reejecuta .\\local_engine_windows\\run_local_engine.bat para instalar dependencias Pro, o fija LOCAL_ENGINE_INFERENCE_BACKEND=chatterbox.${detail}`,
          );
          if (verbose) addLog("Modo Pro: backend en mock (sin clonacion real).");
          lastLoggedDownloadStageRef.current = null;
          return;
        }

        if (download.status === "downloading") {
          const stage = download.stage ?? "downloading";
          const stageLabel = PRO_DOWNLOAD_STAGE_LABELS[stage] ?? stage;
          const stageMessage =
            stage === "initializing_backend"
              ? "Inicializando backend real y cacheando checkpoints (primera vez puede tardar varios minutos)..."
              : "Descargando modelo Pro...";
          setEngineStatus("downloading");
          setEngineNote(`${stageMessage} ${download.progress.toFixed(1)}%.`);
          setProgress({
            status: `${stageMessage} [fase: ${stageLabel}]`,
            progress: download.progress,
          });
          if (lastLoggedDownloadStageRef.current !== stage) {
            addLog(`Modo Pro: fase de descarga -> ${stageLabel}.`);
            lastLoggedDownloadStageRef.current = stage;
          }
          if (verbose) addLog(`Modo Pro: descarga en curso (${download.progress.toFixed(1)}%).`);
          return;
        }

        if (download.status === "failed") {
          setEngineStatus("error");
          setEngineNote(`Fallo en fase ${download.stage ?? "desconocida"}: ${download.error || "sin detalle"}`);
          const currentError = `fase=${download.stage ?? "unknown"} | ${download.error || "La descarga fallo."}`;
          if (lastLoggedDownloadErrorRef.current !== currentError) {
            addLog(`Modo Pro ERROR: descarga fallida -> ${currentError}`);
            lastLoggedDownloadErrorRef.current = currentError;
          }
          lastLoggedDownloadStageRef.current = null;
          if (verbose) addLog(`Modo Pro: descarga fallida (${download.error ?? "sin detalle"}).`);
          return;
        }

        if (capabilities.loaded_profile === PRO_MODEL_PROFILE) {
          setEngineStatus("ready");
          setEngineNote("Motor local listo para sintesis y clonacion.");
          lastLoggedDownloadErrorRef.current = null;
          lastLoggedDownloadStageRef.current = null;
          if (verbose) addLog("Modo Pro: motor listo.");
          return;
        }

        setEngineStatus("stopped");
        if (download.status === "completed") {
          setEngineNote("Modelo descargado. Falta cargarlo en memoria.");
          if (verbose) addLog("Modo Pro: modelo descargado, pendiente de cargar.");
        } else {
          setEngineNote("Motor detectado. Modelo no descargado.");
          if (verbose) addLog("Modo Pro: motor detectado, modelo pendiente de descarga.");
        }
        lastLoggedDownloadStageRef.current = null;
      } catch (error) {
        setEngineStatus("error");
        if (error instanceof LocalEngineError) {
          setEngineNote(`API local ${error.status} - ${error.code}: ${error.message}`);
          if (verbose) addLog(`Modo Pro: ${error.code} (${error.status}).`);
        } else {
          setEngineNote("Error de conexion con API local.");
          if (verbose) addLog("Modo Pro: error inesperado consultando estado.");
        }
      }
    },
    [addLog, engineToken, engineUrl],
  );

  const ensureProModelReady = useCallback(
    async (verbose = false) => {
      if (!engineToken.trim()) {
        setEngineStatus("stopped");
        setEngineNote("Introduce el token local antes de preparar el modo Pro.");
        throw new Error("Introduce el token local del motor Pro.");
      }

      try {
        await localEngineClient.health(engineUrl);
      } catch {
        const message =
          "Motor local no detectado. Descargalo/arrancalo con .\\local_engine_windows\\run_local_engine.bat y vuelve a comprobar.";
        setEngineStatus("not_installed");
        setEngineNote(message);
        throw new Error(message);
      }

      setIsPreparingPro(true);
      try {
        let capabilities = await localEngineClient.capabilities(engineUrl, engineToken);
        setEngineCapabilities(capabilities);

        if (capabilities.inference_backend === "mock") {
          const detail = capabilities.real_backend_error
            ? ` Motivo: ${capabilities.real_backend_error}`
            : "";
          const message = `El motor local esta en modo mock y no permite clonacion real.${detail}`;
          setEngineStatus("error");
          setEngineNote(message);
          throw new Error(message);
        }

        if (capabilities.loaded_profile === PRO_MODEL_PROFILE) {
          setEngineStatus("ready");
          setEngineNote("Motor local listo para sintesis y clonacion.");
          return;
        }

        let download = await localEngineClient.downloadStatus(engineUrl, engineToken, PRO_MODEL_PROFILE);
        setDownloadState(download);

        if (download.status === "failed") {
          throw new Error(
            `Fallo en fase ${download.stage ?? "desconocida"}: ${download.error || "sin detalle"}`,
          );
        }

        if (download.status !== "completed") {
          if (download.status === "idle") {
            addLog("Modo Pro: modelo no descargado, iniciando descarga automatica...");
            await localEngineClient.downloadModel(engineUrl, engineToken, PRO_MODEL_PROFILE);
          } else if (verbose) {
            addLog("Modo Pro: reusando descarga ya iniciada.");
          }

          while (true) {
            await new Promise((resolve) => window.setTimeout(resolve, 850));
            download = await localEngineClient.downloadStatus(engineUrl, engineToken, PRO_MODEL_PROFILE);
            setDownloadState(download);

            if (download.status === "failed") {
              throw new Error(
                `Fallo en fase ${download.stage ?? "desconocida"}: ${download.error || "sin detalle"}`,
              );
            }

            if (download.status === "completed") {
              addLog("Modo Pro: descarga del modelo completada.");
              break;
            }

            const stage = download.stage ?? "downloading";
            const stageLabel = PRO_DOWNLOAD_STAGE_LABELS[stage] ?? stage;
            setEngineStatus("downloading");
            setEngineNote(
              `Preparando modelo Pro... ${download.progress.toFixed(1)}% (fase: ${stageLabel}).`,
            );
            setProgress({
              status: `Preparando modelo Pro [${stageLabel}]`,
              progress: download.progress,
            });
          }
        }

        setProgress({ status: "Cargando modelo Pro en memoria..." });
        await localEngineClient.loadModel(engineUrl, engineToken, PRO_MODEL_PROFILE);
        capabilities = await localEngineClient.capabilities(engineUrl, engineToken);
        setEngineCapabilities(capabilities);
        setEngineStatus("ready");
        setEngineNote("Motor local listo para sintesis y clonacion.");
        addLog("Modo Pro: modelo cargado y listo.");
      } finally {
        setIsPreparingPro(false);
        setProgress(null);
      }
    },
    [addLog, engineToken, engineUrl],
  );

  useEffect(() => {
    localStorage.setItem("local_engine_token", engineToken);
  }, [engineToken]);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  useEffect(() => {
    workerRef.current = new Worker(new URL("./worker.js", import.meta.url), {
      type: "module",
    });

    workerRef.current.onmessage = (event) => {
      const message = event.data;
      if (message.status === "log") {
        addLog(message.message);
      } else if (message.status === "loading") {
        setProgress({ status: "Inicializando motor rapido..." });
      } else if (message.status === "progress") {
        const payload = message.data as { status?: string; progress?: number; file?: string };
        if (payload.status === "downloading") {
          setProgress({
            status: `Descargando ${payload.file ?? "modelo"}...`,
            progress: payload.progress,
          });
        } else if (payload.status === "done") {
          setProgress({ status: "Descarga completada", progress: 100 });
        }
      } else if (message.status === "generating") {
        setProgress({ status: "Inferencia activa en navegador (WebGPU/WASM)..." });
      } else if (message.status === "complete") {
        if (audioUrl) URL.revokeObjectURL(audioUrl);
        setAudioUrl(message.audio as string);
        setProgress(null);
        setIsProcessing(false);
        addLog("Modo rapido: audio generado.");
      } else if (message.status === "error") {
        setProgress({ status: "Error en modo rapido." });
        setIsProcessing(false);
        addLog(`Modo rapido ERROR: ${message.error as string}`);
      }
    };

    addLog("Sistema iniciado. Worker de modo rapido en espera.");
    return () => workerRef.current?.terminate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!PRO_ENABLED || mode !== "pro" || isPreparingPro) return;
    void refreshEngineStatus(true);
    const intervalId = window.setInterval(() => {
      void refreshEngineStatus(false);
    }, 3000);
    return () => window.clearInterval(intervalId);
  }, [isPreparingPro, mode, refreshEngineStatus]);

  useEffect(() => {
    if (mode === "quick") {
      setDefaultQuickText(quickVoice);
      setReferenceAudio(null);
    } else {
      setDefaultProText(proLanguage);
    }
  }, [mode, proLanguage, quickVoice, setDefaultProText, setDefaultQuickText]);

  const handleQuickVoiceChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextVoice = event.target.value as QuickVoice;
    setQuickVoice(nextVoice);
    setDefaultQuickText(nextVoice);
  };

  const handleReferenceAudioChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setReferenceAudio(file);
    if (file) {
      addLog(`Modo Pro: referencia cargada (${file.name}).`);
    }
  };

  const resetProAdvancedSettings = () => {
    setProCfgWeight(PRO_ADVANCED_DEFAULTS.cfgWeight);
    setProExaggeration(PRO_ADVANCED_DEFAULTS.exaggeration);
    setProTemperature(PRO_ADVANCED_DEFAULTS.temperature);
    setProSeedInput("");
    addLog("Modo Pro: ajustes avanzados restablecidos (recomendados).");
  };

  const buildProAdvancedOptions = () => {
    const cfgWeight = Number.isFinite(proCfgWeight) ? proCfgWeight : PRO_ADVANCED_DEFAULTS.cfgWeight;
    const exaggeration = Number.isFinite(proExaggeration) ? proExaggeration : PRO_ADVANCED_DEFAULTS.exaggeration;
    const temperature = Number.isFinite(proTemperature) ? proTemperature : PRO_ADVANCED_DEFAULTS.temperature;

    if (cfgWeight < PRO_CFG_WEIGHT_RANGE.min || cfgWeight > PRO_CFG_WEIGHT_RANGE.max) {
      throw new Error(`cfg_weight fuera de rango (${PRO_CFG_WEIGHT_RANGE.min}-${PRO_CFG_WEIGHT_RANGE.max}).`);
    }
    if (exaggeration < PRO_EXAGGERATION_RANGE.min || exaggeration > PRO_EXAGGERATION_RANGE.max) {
      throw new Error(`exaggeration fuera de rango (${PRO_EXAGGERATION_RANGE.min}-${PRO_EXAGGERATION_RANGE.max}).`);
    }
    if (temperature < PRO_TEMPERATURE_RANGE.min || temperature > PRO_TEMPERATURE_RANGE.max) {
      throw new Error(`temperature fuera de rango (${PRO_TEMPERATURE_RANGE.min}-${PRO_TEMPERATURE_RANGE.max}).`);
    }

    const seedRaw = proSeedInput.trim();
    let seed: number | undefined;
    if (seedRaw.length > 0) {
      const parsed = Number(seedRaw);
      if (!Number.isInteger(parsed) || parsed < 0 || parsed > 2_147_483_647) {
        throw new Error("seed debe ser un entero entre 0 y 2147483647.");
      }
      seed = parsed;
    }

    return {
      cfg_weight: cfgWeight,
      exaggeration,
      temperature,
      seed,
    };
  };

  const handleStartDownload = async () => {
    if (engineStatus === "not_installed") {
      const message =
        "Motor local no detectado. Inicia .\\local_engine_windows\\run_local_engine.bat y vuelve a comprobar.";
      addLog(`Modo Pro ERROR: ${message}`);
      setEngineNote(message);
      setEngineStatus("not_installed");
      return;
    }
    if (!engineToken.trim()) {
      const message = "Introduce el token local antes de descargar el modelo.";
      addLog(`Modo Pro ERROR: ${message}`);
      setEngineNote(message);
      setEngineStatus("stopped");
      return;
    }
    try {
      addLog("Modo Pro: iniciando descarga del modelo...");
      await localEngineClient.downloadModel(engineUrl, engineToken, PRO_MODEL_PROFILE);
      await refreshEngineStatus(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error iniciando descarga.";
      addLog(`Modo Pro ERROR: ${message}`);
      setEngineStatus("error");
      setEngineNote(message);
    }
  };

  const handleLoadModel = async () => {
    try {
      addLog("Modo Pro: cargando modelo en memoria...");
      setProgress({ status: "Cargando modelo Pro en memoria..." });
      await localEngineClient.loadModel(engineUrl, engineToken, PRO_MODEL_PROFILE);
      await refreshEngineStatus(true);
      setProgress(null);
      addLog("Modo Pro: modelo cargado.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error cargando modelo.";
      addLog(`Modo Pro ERROR: ${message}`);
      setProgress(null);
      setEngineStatus("error");
      setEngineNote(message);
    }
  };

  const handleUnloadModel = async () => {
    try {
      addLog("Modo Pro: liberando RAM (descargando modelo de memoria)...");
      await localEngineClient.unloadModel(engineUrl, engineToken, PRO_MODEL_PROFILE);
      await refreshEngineStatus(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error descargando modelo.";
      addLog(`Modo Pro ERROR: ${message}`);
      setEngineStatus("error");
      setEngineNote(message);
    }
  };

  const generateQuick = () => {
    if (!workerRef.current) return;
    workerRef.current.postMessage({
      text,
      voiceId: quickVoice,
    });
  };

  const generatePro = async () => {
    await ensureProModelReady(false);

    const advancedOptions = buildProAdvancedOptions();
    const payload = {
      text,
      language: proLanguage,
      quality_profile: PRO_MODEL_PROFILE,
      ...advancedOptions,
    };

    const requestId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    addLog(`Modo Pro: request_id=${requestId}.`);
    addLog(
      `Modo Pro: parametros -> cfg_weight=${advancedOptions.cfg_weight.toFixed(2)}, exaggeration=${advancedOptions.exaggeration.toFixed(2)}, temperature=${advancedOptions.temperature.toFixed(2)}, seed=${advancedOptions.seed ?? "auto"}.`,
    );
    setProgress({ status: "Generando audio en motor local...", progress: 1 });

    const phaseLabels: Record<string, string> = {
      start: "inicio",
      initializing_backend: "inicializando backend",
      preparing_reference: "preparando referencia",
      sampling: "sampling",
      serializing_audio: "serializando audio",
      completed: "completado",
      failed: "fallo",
    };

    let pollCursor = 0;
    let pollingActive = true;
    let pollingErrored = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    const handleInferenceEvents = (events: EngineEvent[]) => {
      for (const event of events) {
        const phaseLabel = phaseLabels[event.phase] ?? event.phase;
        const level = event.level?.toLowerCase?.() === "error" ? "ERROR " : "";
        addLog(`Modo Pro ${level}[${phaseLabel}]: ${event.message}`);
        if (event.progress !== undefined) {
          setProgress({
            status: `Modo Pro [${phaseLabel}]: ${event.message}`,
            progress: event.progress,
          });
        } else {
          setProgress({
            status: `Modo Pro [${phaseLabel}]: ${event.message}`,
          });
        }
      }
    };

    const pollInferenceEvents = async () => {
      if (!pollingActive) return;
      try {
        const result = await localEngineClient.pollEvents(engineUrl, engineToken, {
          cursor: pollCursor,
          request_id: requestId,
          limit: 200,
        });
        pollCursor = result.next_cursor;
        handleInferenceEvents(result.events);
      } catch (error) {
        if (!pollingErrored) {
          const message = error instanceof Error ? error.message : "error desconocido";
          addLog(`Modo Pro WARN: no se pudieron leer eventos en vivo (${message}).`);
          pollingErrored = true;
        }
      } finally {
        if (pollingActive) {
          pollTimer = setTimeout(() => {
            void pollInferenceEvents();
          }, 450);
        }
      }
    };

    const stopPolling = async () => {
      pollingActive = false;
      if (pollTimer) clearTimeout(pollTimer);
      try {
        const result = await localEngineClient.pollEvents(engineUrl, engineToken, {
          cursor: pollCursor,
          request_id: requestId,
          limit: 200,
        });
        pollCursor = result.next_cursor;
        handleInferenceEvents(result.events);
      } catch {
        // Best-effort flush.
      }
    };

    void pollInferenceEvents();

    let blob: Blob;
    try {
      if (referenceAudio) {
        addLog("Modo Pro: clonacion real desde audio de referencia.");
        blob = await localEngineClient.clone(engineUrl, engineToken, {
          ...payload,
          request_id: requestId,
          reference_audio: referenceAudio,
        });
      } else {
        addLog("Modo Pro: sintesis local sin referencia.");
        blob = await localEngineClient.synthesize(engineUrl, engineToken, {
          ...payload,
          request_id: requestId,
        });
      }
    } finally {
      await stopPolling();
    }

    if (audioUrl) URL.revokeObjectURL(audioUrl);
    const url = URL.createObjectURL(blob);
    setAudioUrl(url);
    setProgress(null);
    addLog("Modo Pro: audio generado correctamente.");
  };

  const handleAutoPreparePro = async () => {
    try {
      addLog("Modo Pro: preparando flujo automatico (motor + modelo)...");
      await ensureProModelReady(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error preparando Modo Pro.";
      addLog(`Modo Pro ERROR: ${message}`);
      setEngineStatus("error");
      setEngineNote(message);
    }
  };

  const handleGenerate = async () => {
    if (!text.trim()) return;
    setLogs([]);
    setAudioUrl(null);
    setIsProcessing(true);
    addLog("Solicitud de generacion recibida.");

    try {
      if (mode === "quick") {
        generateQuick();
      } else {
        await generatePro();
        setIsProcessing(false);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error durante la generacion.";
      addLog(`ERROR: ${message}`);
      setProgress({ status: message });
      setIsProcessing(false);
    }
  };

  const modeDescription =
    mode === "quick"
      ? "Modo rapido: ejecucion 100% en navegador."
      : "Modo Pro: motor local para maxima calidad y clonacion real.";

  return (
    <div className="app-container">
      <header>
        <h1>Studio Voice AI</h1>
        <p>Texto a voz con modo rapido y modo Pro local para maxima calidad.</p>
      </header>

      <main className="glass-card">
        <div className="alert-box">
          <AlertTriangle color="#eab308" className="shrink-0" />
          <div>
            <strong>Descargas pesadas en Modo Pro</strong>
            <p>
              El modo Pro puede requerir descargas grandes para habilitar clonacion real y mas calidad.
              Railway se usa como control plane; la inferencia pesada ocurre en tu equipo.
            </p>
          </div>
        </div>

        <div className="mode-switch">
          <label>Modo de ejecucion</label>
          <div className="mode-buttons">
            <button
              type="button"
              className={`mode-btn ${mode === "quick" ? "active" : ""}`}
              onClick={() => setMode("quick")}
            >
              <Cpu size={16} /> Modo Rapido
            </button>
            <button
              type="button"
              className={`mode-btn ${mode === "pro" ? "active" : ""}`}
              onClick={() => setMode("pro")}
              disabled={!PRO_ENABLED}
            >
              <Server size={16} /> Modo Pro
            </button>
          </div>
          <small>{modeDescription}</small>
        </div>

        {mode === "quick" && (
          <div className="control-group">
            <label htmlFor="voice-select">Voz rapida (navegador)</label>
            <select id="voice-select" value={quickVoice} onChange={handleQuickVoiceChange}>
              <optgroup label="MMS nativo">
                <option value="spa">Espanol (MMS VITS)</option>
                <option value="eng">Ingles (MMS VITS)</option>
              </optgroup>
              <optgroup label="SpeechT5 perfiles predefinidos">
                <option value="clone_f1">Clon predefinido F1</option>
                <option value="clone_f2">Clon predefinido F2</option>
                <option value="clone_m1">Clon predefinido M1</option>
                <option value="clone_m2">Clon predefinido M2</option>
              </optgroup>
            </select>
          </div>
        )}

        {mode === "pro" && (
          <>
            <div className="engine-panel">
              <div className="engine-header">
                <strong>Motor local Pro (localhost)</strong>
                <span className={`engine-status ${currentStatusClass}`}>{engineStatus}</span>
              </div>
              <p className="engine-note">{engineNote}</p>
              <div className="engine-download-cta">
                <p className="engine-note">
                  <strong>Quieres usar el modelo Pro?</strong> Descarga el Local Engine para ejecutar la parte pesada
                  fuera del navegador, evitar bloqueos de memoria y mejorar rendimiento.
                </p>
                <a
                  className="btn-secondary"
                  href={LOCAL_ENGINE_WINDOWS_INSTALLER_URL}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Download size={16} /> Descargar Local Engine (.exe)
                </a>
                <small className="help-text">
                  Pasos: 1) Descarga y ejecuta el <code>.exe</code>. 2) Copia el token de la ventana local.
                  3) Pegalo aqui y pulsa <code>Preparar modo Pro</code>.
                </small>
              </div>

              <div className="controls-row">
                <div className="control-group">
                  <label htmlFor="engine-url">URL del motor local</label>
                  <input
                    id="engine-url"
                    value={engineUrl}
                    onChange={(event) => setEngineUrl(event.target.value)}
                    placeholder="http://127.0.0.1:57641"
                  />
                </div>
                <div className="control-group">
                  <label htmlFor="engine-token">Token local</label>
                  <input
                    id="engine-token"
                    type="password"
                    value={engineToken}
                    onChange={(event) => setEngineToken(event.target.value)}
                    placeholder="Pega aqui tu token local"
                  />
                </div>
              </div>

              <div className="engine-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => void handleAutoPreparePro()}
                  disabled={isPreparingPro || isProcessing}
                >
                  {isPreparingPro ? <Loader2 className="animate-spin" size={16} /> : <Server size={16} />} Preparar
                  modo Pro
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => void refreshEngineStatus(true)}
                  disabled={isPreparingPro || isProcessing}
                >
                  <RefreshCw size={16} /> Comprobar motor
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => void handleStartDownload()}
                  disabled={isPreparingPro || isProcessing}
                >
                  <Download size={16} /> Descargar modelo Pro
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => void handleLoadModel()}
                  disabled={isPreparingPro || isProcessing}
                >
                  <Server size={16} /> Cargar modelo
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => void handleUnloadModel()}
                  disabled={isPreparingPro || isProcessing}
                >
                  <Server size={16} /> Liberar RAM
                </button>
              </div>
              <small className="help-text">`Liberar RAM` no borra el modelo en disco; solo lo descarga de memoria.</small>

              {downloadState && (
                <div className="download-info">
                  <strong>Descarga:</strong> {downloadState.status} ({downloadState.progress.toFixed(1)}%)
                </div>
              )}

              {engineCapabilities && (
                <div className="capability-info">
                  Plataforma: {engineCapabilities.platform} | GPU:{" "}
                  {engineCapabilities.gpu_available ? "disponible" : "no detectada"} | Perfil cargado:{" "}
                  {engineCapabilities.loaded_profile ?? "ninguno"} | Backend:{" "}
                  {engineCapabilities.inference_backend ?? "desconocido"}
                </div>
              )}
            </div>

            <div className="controls-row">
              <div className="control-group">
                <label htmlFor="pro-language">Idioma Pro</label>
                <select
                  id="pro-language"
                  value={proLanguage}
                  onChange={(event) => setProLanguage(event.target.value as ProLanguage)}
                >
                  <option value="es">Espanol</option>
                  <option value="en">English</option>
                </select>
              </div>
              <div className="control-group">
                <label htmlFor="reference-audio">Audio de referencia (clonacion real)</label>
                <label className="upload-field" htmlFor="reference-audio">
                  <UploadCloud size={16} />
                  {referenceAudio ? referenceAudio.name : "Seleccionar WAV/MP3 opcional"}
                </label>
                <input
                  id="reference-audio"
                  type="file"
                  accept="audio/wav,audio/mpeg,audio/mp3,audio/x-wav"
                  onChange={handleReferenceAudioChange}
                  className="hidden-input"
                />
              </div>
            </div>

            <div className="advanced-panel">
              <div className="engine-header">
                <strong>Ajustes avanzados Pro</strong>
                <button type="button" className="btn-secondary" onClick={resetProAdvancedSettings}>
                  Restablecer recomendados
                </button>
              </div>
              <div className="controls-row">
                <div className="control-group">
                  <label htmlFor="pro-cfg-weight">cfg_weight ({proCfgWeight.toFixed(2)})</label>
                  <input
                    id="pro-cfg-weight"
                    type="number"
                    min={PRO_CFG_WEIGHT_RANGE.min}
                    max={PRO_CFG_WEIGHT_RANGE.max}
                    step={PRO_CFG_WEIGHT_RANGE.step}
                    value={proCfgWeight}
                    onChange={(event) => {
                      const next = event.target.valueAsNumber;
                      setProCfgWeight(Number.isFinite(next) ? next : PRO_ADVANCED_DEFAULTS.cfgWeight);
                    }}
                  />
                  <small className="help-text">Guiado del texto frente a estilo de voz.</small>
                </div>
                <div className="control-group">
                  <label htmlFor="pro-exaggeration">exaggeration ({proExaggeration.toFixed(2)})</label>
                  <input
                    id="pro-exaggeration"
                    type="number"
                    min={PRO_EXAGGERATION_RANGE.min}
                    max={PRO_EXAGGERATION_RANGE.max}
                    step={PRO_EXAGGERATION_RANGE.step}
                    value={proExaggeration}
                    onChange={(event) => {
                      const next = event.target.valueAsNumber;
                      setProExaggeration(Number.isFinite(next) ? next : PRO_ADVANCED_DEFAULTS.exaggeration);
                    }}
                  />
                  <small className="help-text">Expresividad y color emocional de la voz.</small>
                </div>
                <div className="control-group">
                  <label htmlFor="pro-temperature">temperature ({proTemperature.toFixed(2)})</label>
                  <input
                    id="pro-temperature"
                    type="number"
                    min={PRO_TEMPERATURE_RANGE.min}
                    max={PRO_TEMPERATURE_RANGE.max}
                    step={PRO_TEMPERATURE_RANGE.step}
                    value={proTemperature}
                    onChange={(event) => {
                      const next = event.target.valueAsNumber;
                      setProTemperature(Number.isFinite(next) ? next : PRO_ADVANCED_DEFAULTS.temperature);
                    }}
                  />
                  <small className="help-text">Variabilidad del muestreo (mas alto = mas creativo).</small>
                </div>
                <div className="control-group">
                  <label htmlFor="pro-seed">seed (opcional)</label>
                  <input
                    id="pro-seed"
                    type="number"
                    min={0}
                    max={2147483647}
                    step={1}
                    value={proSeedInput}
                    onChange={(event) => setProSeedInput(event.target.value)}
                    placeholder="vacio = aleatorio"
                  />
                  <small className="help-text">Fija una semilla para resultados reproducibles.</small>
                </div>
              </div>
            </div>
          </>
        )}

        <div className="control-group">
          <label htmlFor="text-input">Texto a sintetizar</label>
          <textarea
            id="text-input"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Escribe aqui el texto..."
            maxLength={700}
          />
          <div className="char-counter">{text.length} / 700 caracteres</div>
        </div>

        <button
          className="btn-primary"
          onClick={() => void handleGenerate()}
          disabled={isProcessing || isPreparingPro || !text.trim()}
        >
          {isProcessing ? (
            <>
              <Loader2 className="animate-spin" size={20} />
              Procesando...
            </>
          ) : (
            <>
              <Play size={20} />
              Generar voz
            </>
          )}
        </button>
        {mode === "pro" && (
          <small className="help-text">
            En Modo Pro, `Generar voz` prepara automaticamente el modelo (descarga + carga) si todavia no esta listo.
          </small>
        )}

        <div>
          <label className="console-label">
            <Terminal size={14} /> Consola de ejecucion
          </label>
          <div className="console-box">
            {logs.length === 0 ? <span className="console-placeholder">Esperando eventos...</span> : null}
            {logs.map((line, index) => (
              <div key={`${line}-${index}`}>{line}</div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>

        {progress && progress.progress !== undefined && (
          <div className="status-bar">
            <div className="progress-container">
              <div className="progress-bar" style={{ width: `${progress.progress}%` }} />
            </div>
            <div className="status-text">
              {progress.status} ({Math.round(progress.progress)}%)
            </div>
          </div>
        )}

        {progress && progress.progress === undefined && (
          <div className="status-text" style={{ marginTop: "-0.5rem" }}>
            {progress.status}
          </div>
        )}

        {audioUrl && (
          <div className="audio-player-container">
            <label className="audio-ready-label">Sintesis completada</label>
            <audio src={audioUrl} controls autoPlay />
            <div className="audio-actions">
              <a href={audioUrl} download={`voice_${Date.now()}.wav`} className="btn-secondary">
                <Download size={16} /> Descargar
              </a>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
