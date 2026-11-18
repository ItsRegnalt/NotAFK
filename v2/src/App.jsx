import React, { useState, useEffect, useRef } from 'react';
import {
  Play,
  Square,
  Plus,
  Save,
  Pencil,
  FolderOpen,
  MousePointer,
  Move,
  Type,
  Clock,
  Trash2,
  Copy,
  GripVertical,
  Crosshair,
  Timer,
  BrainCircuit,
  Repeat,
  Activity,
  ChevronDown,
  Check,
  AlertTriangle,
  Sparkles,
  Minus,
  Maximize2,
  X,
  Sliders,
  Keyboard,
  AppWindow,
  Settings,
  Upload,
  Download,
  Circle,
  ArrowUpDown,
  Hand,
  ShieldCheck
} from 'lucide-react';

// Last session (steps, settings, target) so the app opens where the user left it; first run starts empty.
const SESSION = (() => {
  try { return JSON.parse(localStorage.getItem('notafk.session') || 'null') || {}; } catch { return {}; }
})();
const saved = (key, fallback) => SESSION.settings?.[key] ?? fallback;
const dropRemoved = (list) => (Array.isArray(list) ? list.filter((step) => step?.type !== 'wait') : []); // 'Wait for color' was removed
const DEFAULT_PREFS = { hotkeyStart: 'F6', hotkeyStop: 'F7', minimizeOnStart: false, askAdmin: true, checkUpdates: true };
const F_KEYS = Array.from({ length: 12 }, (_, i) => `F${i + 1}`);

const PALETTE = [
  ['click', 'Click', MousePointer, 'text-blue-400'],
  ['key', 'Key', Keyboard, 'text-emerald-400'],
  ['text', 'Text', Type, 'text-purple-400'],
  ['move', 'Move', Move, 'text-cyan-400'],
  ['delay', 'Delay', Clock, 'text-amber-400'],
  ['scroll', 'Scroll', ArrowUpDown, 'text-teal-400'],
  ['drag', 'Drag', Hand, 'text-orange-400'],
  ['loop', 'Repeat', Repeat, 'text-sky-400'],
];

// Qt edge flags (Top=1, Left=2, Right=4, Bottom=8) for frameless window resize handles
const RESIZE_EDGES = [
  ['top-0 left-2 right-2 h-1.5 cursor-ns-resize', 1],
  ['bottom-0 left-2 right-2 h-1.5 cursor-ns-resize', 8],
  ['left-0 top-2 bottom-2 w-1.5 cursor-ew-resize', 2],
  ['right-0 top-2 bottom-2 w-1.5 cursor-ew-resize', 4],
  ['top-0 left-0 w-2.5 h-2.5 cursor-nwse-resize', 3],
  ['top-0 right-0 w-2.5 h-2.5 cursor-nesw-resize', 5],
  ['bottom-0 left-0 w-2.5 h-2.5 cursor-nesw-resize', 10],
  ['bottom-0 right-0 w-2.5 h-2.5 cursor-nwse-resize', 12],
];

const KEY_OPTIONS = [
  ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
  ...'0123456789',
  ...Array.from({ length: 12 }, (_, i) => `F${i + 1}`),
  'Space', 'Enter', 'Tab', 'Escape', 'Backspace', 'Delete',
  'Arrow Up', 'Arrow Down', 'Arrow Left', 'Arrow Right',
  'Home', 'End', 'Page Up', 'Page Down', 'Insert',
  'Shift', 'Ctrl', 'Alt', 'Win',
];
const MODIFIER_KEYS = ['Ctrl', 'Shift', 'Alt', 'Win'];

export default function App() {
  // Macro Steps State
  const [steps, setSteps] = useState(dropRemoved(SESSION.steps));
  const [selectedMacro, setSelectedMacro] = useState(SESSION.name || 'New Automation');
  const [recentMacros, setRecentMacros] = useState(() => {
    try {
      return Object.keys(JSON.parse(localStorage.getItem('notafk.macros') || '{}'))
        .slice(0, 3).map((name) => ({ id: `saved-${name}`, name, tag: 'Saved' }));
    } catch { return []; }
  });
  const [savedMacros, setSavedMacros] = useState(() => {
    try { return JSON.parse(localStorage.getItem('notafk.macros') || '{}'); }
    catch { return {}; }
  });
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [dialog, setDialog] = useState(null); // { kind: 'rename' | 'delete', name, value }
  const [pickingStepId, setPickingStepId] = useState(null);
  const [activeStepIndex, setActiveStepIndex] = useState(null);
  const [draggedStepId, setDraggedStepId] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);
  const [toast, setToast] = useState(null);
  const dragPreviewRef = useRef(null);
  const dragOffsetRef = useRef({ x: 0, y: 0 });
  const dropTargetRef = useRef(null);

  useEffect(() => {
    if (!draggedStepId) return undefined;
    const movePreview = (event) => {
      if (dragPreviewRef.current) {
        dragPreviewRef.current.style.left = `${event.clientX - dragOffsetRef.current.x}px`;
        dragPreviewRef.current.style.top = `${event.clientY - dragOffsetRef.current.y}px`;
      }
      const cards = [...document.querySelectorAll('[data-step-id]')]
        .filter((card) => card.dataset.stepId !== draggedStepId);
      const previous = dropTargetRef.current;
      const previousCard = cards.find((card) => card.dataset.stepId === previous?.id);
      if (previousCard) {
        const rect = previousCard.getBoundingClientRect();
        const midpoint = rect.top + rect.height / 2;
        if (Math.abs(event.clientY - midpoint) <= 20) return;
      }
      const nextCard = cards.find((card) => {
        const rect = card.getBoundingClientRect();
        return event.clientY < rect.top + rect.height / 2;
      });
      const target = nextCard || cards.at(-1);
      const nextDropTarget = target && {
        id: target.dataset.stepId,
        position: nextCard ? 'before' : 'after',
      };
      if (previous?.id !== nextDropTarget?.id || previous?.position !== nextDropTarget?.position) {
        dropTargetRef.current = nextDropTarget;
        setDropTarget(nextDropTarget);
      }
    };
    const finishDrag = () => {
      const target = dropTargetRef.current;
      if (target) reorderSteps(draggedStepId, target.id, target.position);
      dragPreviewRef.current?.remove();
      dragPreviewRef.current = null;
      dropTargetRef.current = null;
      setDraggedStepId(null);
      setDropTarget(null);
    };
    window.addEventListener('pointermove', movePreview);
    window.addEventListener('pointerup', finishDrag, { once: true });
    window.addEventListener('pointercancel', finishDrag, { once: true });
    return () => {
      window.removeEventListener('pointermove', movePreview);
      window.removeEventListener('pointerup', finishDrag);
      window.removeEventListener('pointercancel', finishDrag);
    };
  }, [draggedStepId]);

  // Right & Left Sidebar Settings State (matching reference screenshot defaults)
  const [minDelay, setMinDelay] = useState(saved('minDelay', '0,70'));
  const [maxDelay, setMaxDelay] = useState(saved('maxDelay', '0,98'));
  const [globalDelayEnabled, setGlobalDelayEnabled] = useState(saved('globalDelayEnabled', true));
  const [movementEnabled, setMovementEnabled] = useState(saved('movementEnabled', true));
  const [backgroundEnabled, setBackgroundEnabled] = useState(saved('backgroundEnabled', false));
  const [target, setTarget] = useState(SESSION.target || null); // { hwnd, title } window that receives background input
  const [mouseSpeed, setMouseSpeed] = useState(saved('mouseSpeed', '1,0'));
  const [curvePercent, setCurvePercent] = useState(saved('curvePercent', 25));
  const [targetJitter, setTargetJitter] = useState(saved('targetJitter', '3'));
  const [runMode, setRunMode] = useState(saved('runMode', 'repeat')); // 'once' | 'repeat' | 'loop'
  const [repeatCount, setRepeatCount] = useState(saved('repeatCount', 10));
  const [timeLimit, setTimeLimit] = useState(saved('timeLimit', '')); // minutes, '' = no limit
  const [isRecording, setIsRecording] = useState(false);
  const [countdown, setCountdown] = useState(null); // 3, 2, 1 before recording starts
  const countdownTimer = useRef(null);
  const [targetMenu, setTargetMenu] = useState(null); // open windows list for the background target dropdown
  const [showSettings, setShowSettings] = useState(false);
  const [appInfo, setAppInfo] = useState(null); // { admin, version, updates, test } from the desktop shell
  const [adminPrompt, setAdminPrompt] = useState(false);
  const [adminDontAsk, setAdminDontAsk] = useState(false);
  const [update, setUpdate] = useState(null); // latest release when it is newer than this app
  const [updating, setUpdating] = useState(false);
  const [prefs, setPrefs] = useState(() => {
    try { return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem('notafk.prefs') || '{}') }; }
    catch { return DEFAULT_PREFS; }
  });

  // Settings that belong to an automation (saved / exported together with its steps)
  const currentSettings = () => ({
    minDelay, maxDelay, globalDelayEnabled, movementEnabled, mouseSpeed, curvePercent,
    targetJitter, runMode, repeatCount, timeLimit, backgroundEnabled,
  });
  const SETTERS = {
    minDelay: setMinDelay, maxDelay: setMaxDelay, globalDelayEnabled: setGlobalDelayEnabled,
    movementEnabled: setMovementEnabled, mouseSpeed: setMouseSpeed, curvePercent: setCurvePercent,
    targetJitter: setTargetJitter, runMode: setRunMode, repeatCount: setRepeatCount,
    timeLimit: setTimeLimit, backgroundEnabled: setBackgroundEnabled,
  };
  const applySettings = (settings) => {
    Object.entries(settings || {}).forEach(([key, value]) => SETTERS[key]?.(value));
  };
  // Older saves stored only the steps array
  const unpackAutomation = (entry) => (Array.isArray(entry) ? { steps: entry, settings: {} } : entry || { steps: [] });
  const loadAutomation = (name) => {
    const { steps: loaded, settings } = unpackAutomation(savedMacros[name]);
    setSteps(dropRemoved(loaded));
    applySettings(settings);
    setSelectedMacro(name);
  };

  useEffect(() => {
    localStorage.setItem('notafk.macros', JSON.stringify(savedMacros));
  }, [savedMacros]);

  useEffect(() => {
    try {
      localStorage.setItem('notafk.session', JSON.stringify({ steps, name: selectedMacro, target, settings: currentSettings() }));
    } catch { /* storage full or blocked: the session is a convenience only */ }
  }, [steps, selectedMacro, target, minDelay, maxDelay, globalDelayEnabled, movementEnabled, mouseSpeed,
    curvePercent, targetJitter, runMode, repeatCount, timeLimit, backgroundEnabled]);

  // Execution / Simulation State & Live Logs
  const [isRunning, setIsRunning] = useState(false);
  const [nativeReady, setNativeReady] = useState(Boolean(window.notafkBridge));
  const [currentCycle, setCurrentCycle] = useState(0);
  const [logs, setLogs] = useState([]);
  const timerRef = useRef(null);

  useEffect(() => {
    const ready = () => setNativeReady(Boolean(window.notafkBridge));
    const onStep = (event) => {
      const idx = steps.findIndex((step) => step.id === event.detail.id);
      if (idx >= 0) {
        setActiveStepIndex(idx);
        const step = steps[idx];
        pushLog(`Step #${idx + 1} [${step.type.toUpperCase()}${step.type === 'key' ? ` ${step.keyName} ${step.keyMode}` : ''}] running`, 'exec');
      }
    };
    const onCycle = (event) => setCurrentCycle(event.detail.current);
    const onStatus = (event) => {
      pushLog(event.detail, event.detail.startsWith('Error:') ? 'warn' : 'exec');
      if (event.detail.startsWith('Status: Running')) setIsRunning(true);
    };
    const onFinished = (event) => {
      setIsRunning(false);
      setActiveStepIndex(null);
      if (prefs.minimizeOnStart) window.notafkBridge?.restoreWindow();
      if (!event.detail) showToast('Automation stopped or failed');
    };
    const onPicked = (event) => {
      const { id, x, y, rel } = event.detail;
      const point = { x, y, picked: true, ...(rel ? { rel } : {}) };
      if (id.endsWith('::to')) updateStep(id.slice(0, -4), { to: point }); // end point of a Drag step
      else updateStep(id, { coords: point });
      setPickingStepId(null);
      pushLog(`Picked screen coords X:${x}, Y:${y}`, 'ready');
      showToast(`Coordinates: X:${x}, Y:${y}`);
    };
    const onPickCancelled = () => setPickingStepId(null);
    const onTarget = (event) => {
      setTarget(event.detail);
      setBackgroundEnabled(true);
      pushLog(`Background target: "${event.detail.title}"`, 'ready');
    };
    window.addEventListener('notafk:target', onTarget);
    const onRecorded = (event) => {
      setIsRecording(false);
      const recorded = event.detail || [];
      if (!recorded.length) return showToast('Nothing was recorded');
      setSteps((prev) => [...prev, ...recorded]);
      pushLog(`Recorded ${recorded.length} steps`, 'ready');
      showToast(`Recorded ${recorded.length} steps`);
    };
    window.addEventListener('notafk:recorded', onRecorded);
    window.addEventListener('notafk:ready', ready);
    window.addEventListener('notafk:step', onStep);
    window.addEventListener('notafk:cycle', onCycle);
    window.addEventListener('notafk:status', onStatus);
    window.addEventListener('notafk:finished', onFinished);
    window.addEventListener('notafk:picked', onPicked);
    window.addEventListener('notafk:pick-cancelled', onPickCancelled);
    return () => {
      window.removeEventListener('notafk:ready', ready);
      window.removeEventListener('notafk:step', onStep);
      window.removeEventListener('notafk:cycle', onCycle);
      window.removeEventListener('notafk:status', onStatus);
      window.removeEventListener('notafk:finished', onFinished);
      window.removeEventListener('notafk:picked', onPicked);
      window.removeEventListener('notafk:pick-cancelled', onPickCancelled);
      window.removeEventListener('notafk:target', onTarget);
      window.removeEventListener('notafk:recorded', onRecorded);
    };
  }, [steps, prefs]);

  // Preferences: persist and hand the hotkeys to the native listener
  useEffect(() => {
    try { localStorage.setItem('notafk.prefs', JSON.stringify(prefs)); } catch { /* convenience only */ }
    if (nativeReady) window.notafkBridge.setHotkeys(prefs.hotkeyStart, prefs.hotkeyStop);
  }, [prefs, nativeReady]);

  // Startup: suggest administrator mode, look for a newer release (not in tests)
  const checkForUpdate = (manual) => Promise.resolve(window.notafkBridge.checkUpdate()).then((info) => {
    if (info?.available) setUpdate(info);
    else if (manual) showToast(info?.error || `NotAFK ${info?.current} is the latest version`);
  });
  useEffect(() => {
    if (!nativeReady) return;
    Promise.resolve(window.notafkBridge.startupInfo()).then((info) => {
      setAppInfo(info);
      if (info.test) return;
      if (!info.admin && prefs.askAdmin) setAdminPrompt(true);
      if (info.updates && prefs.checkUpdates) checkForUpdate(false);
    });
  }, [nativeReady]);

  const restartAsAdmin = () => {
    setAdminPrompt(false);
    Promise.resolve(window.notafkBridge.relaunchAsAdmin()).then((ok) => {
      if (!ok) showToast('Administrator restart was cancelled');
    });
  };

  const installUpdate = () => {
    setUpdating(true);
    Promise.resolve(window.notafkBridge.installUpdate()).then((result) => {
      if (result?.ok) return showToast(`Installing NotAFK ${result.version}…`); // the app closes and restarts
      setUpdating(false);
      showToast(result?.error || 'Update failed');
    });
  };

  // A remembered background target may have a new window handle after a restart
  useEffect(() => {
    if (!nativeReady || !target) return;
    Promise.resolve(window.notafkBridge.resolveTarget(target.hwnd, target.title)).then((hwnd) => {
      if (!hwnd) {
        setTarget(null);
        setBackgroundEnabled(false);
        pushLog(`Background target "${target.title}" is not open; pick it again`, 'warn');
      } else if (hwnd !== target.hwnd) {
        setTarget({ ...target, hwnd });
      }
    });
  }, [nativeReady]);

  const pushLog = (msg, type = 'info') => {
    const now = new Date();
    const time = now.toTimeString().split(' ')[0];
    setLogs((prev) => [{ time, msg, type }, ...prev.slice(0, 14)]);
  };

  // Show temporary notification toast
  const toastTimer = useRef(null);
  const showToast = (msg) => {
    setToast(msg);
    clearTimeout(toastTimer.current); // a newer toast gets its full time
    toastTimer.current = setTimeout(() => setToast(null), 2400);
  };

  // Keyboard shortcuts F6 (Start) & F7/Esc (Stop)
  useEffect(() => {
    if (nativeReady) {
      // Native mode: global F6/F7/Esc come from the Python pynput listener (work while app is unfocused).
      const onHotkey = ({ detail }) => {
        if (detail === 'start') handleStart();
        else if (detail === 'stop' || (detail === 'esc' && isRunning)) handleStop();
      };
      window.addEventListener('notafk:hotkey', onHotkey);
      return () => window.removeEventListener('notafk:hotkey', onHotkey);
    }
    const handleKeyDown = (e) => {
      if (e.key === prefs.hotkeyStart) {
        e.preventDefault();
        handleStart();
      } else if (e.key === prefs.hotkeyStop || (e.key === 'Escape' && isRunning)) {
        e.preventDefault();
        handleStop();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  });

  // Live Execution Simulation
  useEffect(() => {
    if (!isRunning || nativeReady) {
      // Native mode: real step/cycle/finish events come from the bridge, no fake simulation.
      if (!isRunning) setActiveStepIndex(null);
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    const enabledSteps = steps.filter((s) => s.enabled);
    if (enabledSteps.length === 0) {
      setIsRunning(false);
      showToast('Enable at least one step.');
      return;
    }

    let stepIdx = 0;
    let cycle = 1;
    setCurrentCycle(1);
    setActiveStepIndex(0);
    pushLog(`Cycle #1 started (${enabledSteps.length} active steps)`, 'exec');

    timerRef.current = setInterval(() => {
      const currentStep = steps[stepIdx];
      if (currentStep && currentStep.enabled) {
        pushLog(
          `Step #${stepIdx + 1} [${currentStep.type.toUpperCase()}${currentStep.type === 'key' ? ` ${currentStep.keyName} ${currentStep.keyMode}` : ''}] executed${movementEnabled ? ' + movement settings' : ''}${globalDelayEnabled ? ' + global delay' : ''}`,
          'exec'
        );
      }

      stepIdx++;
      if (stepIdx >= steps.length) {
        stepIdx = 0;
        const maxCycles =
          runMode === 'once' ? 1 : runMode === 'repeat' ? Number(repeatCount) || 1 : Infinity;
        if (cycle >= maxCycles) {
          setIsRunning(false);
          setActiveStepIndex(null);
          pushLog('Automation completed successfully.', 'ready');
          showToast('Automation finished.');
          return;
        }
        cycle++;
        setCurrentCycle(cycle);
        pushLog(`Cycle #${cycle} started`, 'info');
      }
      setActiveStepIndex(stepIdx);
    }, 620);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isRunning, steps, runMode, repeatCount, movementEnabled, globalDelayEnabled, nativeReady]);

  const handleStart = () => {
    if (steps.length === 0) {
      showToast('Add a step first.');
      return;
    }
    if (nativeReady && window.notafkBridge) {
      window.notafkBridge.startMacro(JSON.stringify({
        steps, runMode, repeatCount, minDelay, maxDelay, globalDelayEnabled,
        movementEnabled, mouseSpeed, curvePercent, targetJitter,
        backgroundEnabled: backgroundEnabled && Boolean(target), targetHwnd: target?.hwnd, timeLimit,
      }));
      setIsRunning(true);
      pushLog(timeLimit ? `Automation started (stops after ${timeLimit} min)` : 'Automation started', 'exec');
      // Get out of the way of a normal run (a background run does not touch the screen)
      if (prefs.minimizeOnStart && !(backgroundEnabled && target)) window.notafkBridge.minimizeWindow();
      return;
    }
    setIsRunning(true);
    pushLog('Execution triggered via Start (F6)', 'exec');
  };

  const handleStop = () => {
    if (nativeReady && window.notafkBridge) window.notafkBridge.stopMacro();
    if (isRunning) {
      pushLog('Stopped by user', 'warn');
      showToast('Automation stopped');
    }
    setIsRunning(false);
    setActiveStepIndex(null);
  };

  const beginRecording = async () => {
    const ok = await window.notafkBridge.startRecording(backgroundEnabled && target ? target.hwnd : null);
    if (ok) {
      setIsRecording(true);
      pushLog(`Recording... press ${prefs.hotkeyStop} or Esc to finish`, 'exec');
    }
  };

  // Record: 3-2-1 countdown first, then NotAFK minimizes and recording starts. Clicking again cancels.
  const toggleRecording = () => {
    if (!nativeReady) return showToast('Recording works in the desktop app');
    if (isRecording) return window.notafkBridge.stopRecording();
    if (countdown !== null) {
      clearInterval(countdownTimer.current);
      return setCountdown(null);
    }
    if (isRunning) return;
    let left = 3;
    setCountdown(left);
    countdownTimer.current = setInterval(() => {
      left -= 1;
      if (left > 0) return setCountdown(left);
      clearInterval(countdownTimer.current);
      setCountdown(null);
      beginRecording();
    }, 1000);
  };

  const exportAutomation = async () => {
    if (!nativeReady) return showToast('Export works in the desktop app');
    const file = { app: 'NotAFK', version: 1, name: selectedMacro, steps, settings: currentSettings() };
    if (await window.notafkBridge.exportAutomation(JSON.stringify(file, null, 2), selectedMacro)) {
      showToast(`Exported "${selectedMacro}"`);
    }
  };

  const importAutomation = async () => {
    if (!nativeReady) return showToast('Import works in the desktop app');
    const raw = await window.notafkBridge.importAutomation();
    if (!raw) return;
    try {
      const data = JSON.parse(raw);
      if (!Array.isArray(data.steps)) throw new Error('no steps');
      const imported = dropRemoved(data.steps.filter((step) => step && typeof step === 'object' && step.id && step.type));
      let name = String(data.name || 'Imported automation').slice(0, 60);
      for (let i = 2; savedMacros[name]; i += 1) name = `${String(data.name || 'Imported automation').slice(0, 55)} (${i})`;
      setSteps(imported);
      applySettings(data.settings);
      setSelectedMacro(name);
      setSavedMacros((current) => ({ ...current, [name]: { steps: imported, settings: data.settings || {} } }));
      setRecentMacros((current) => [{ id: `saved-${name}`, name, tag: 'Saved' }, ...current.filter((item) => item.name !== name)].slice(0, 3));
      showToast(`Imported "${name}"`);
    } catch {
      showToast('That file is not a NotAFK automation');
    }
  };

  // Add New Step Handlers
  const addStep = (type) => {
    const id = `step-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    let newStep = { id, enabled: true, type };

    if (type === 'click') {
      newStep = {
        ...newStep,
        coords: { x: 960, y: 540, picked: false },
        button: 'Left click',
        times: '1',
        clickInterval: '0,10',
      };
    } else if (type === 'move') {
      newStep = {
        ...newStep,
        coords: { x: 1420, y: 610, picked: false },
      };
    } else if (type === 'text') {
      newStep = {
        ...newStep,
        textValue: 'Hello World',
        keyDelay: '0,05',
        pressEnter: false,
      };
    } else if (type === 'delay') {
      newStep = {
        ...newStep,
        duration: '0,50',
        randomize: true,
        variance: '0,15',
      };
    } else if (type === 'key') {
      newStep = { ...newStep, keyName: 'Space', keyMode: 'press', holdDuration: '0,50' };
    } else if (type === 'drag') {
      newStep = {
        ...newStep, coords: { x: 800, y: 500, picked: false }, to: { x: 1000, y: 500, picked: false },
        button: 'Left click', duration: '0,60',
      };
    } else if (type === 'scroll') {
      newStep = { ...newStep, coords: { x: 960, y: 540, picked: false }, amount: '-3' };
    } else if (type === 'loop') {
      // A repeat block is a pair of rows; the steps dragged between them are repeated
      setSteps((prev) => [...prev, { ...newStep, times: '3' },
        { id: `${id}-end`, enabled: true, type: 'loopEnd', loopOwnerId: id }]);
      pushLog('Added a repeat block', 'info');
      return;
    }

    setSteps((prev) => [...prev, newStep]);
    pushLog(`Added new ${type.toUpperCase()} step (#${steps.length + 1})`, 'info');
  };

  const renameMacro = (oldName, value) => {
    const renamed = value.trim();
    if (!renamed || renamed === oldName) return setDialog(null);
    if (savedMacros[renamed]) return showToast(`"${renamed}" already exists`);
    if (savedMacros[oldName]) {
      setSavedMacros((current) => {
        const next = { ...current, [renamed]: current[oldName] };
        delete next[oldName];
        return next;
      });
    }
    if (selectedMacro === oldName) setSelectedMacro(renamed);
    setRecentMacros((current) => current.map((macro) =>
      macro.name === oldName ? { ...macro, id: `saved-${renamed}`, name: renamed } : macro
    ));
    setDialog(null);
    showToast('Automation renamed');
  };

  const deleteMacro = (name) => {
    setSavedMacros((current) => {
      const next = { ...current };
      delete next[name];
      return next;
    });
    setRecentMacros((current) => current.filter((macro) => macro.name !== name));
    setDialog(null);
    pushLog(`Deleted profile "${name}"`, 'warn');
    showToast(`Deleted "${name}"`);
  };

  const toggleEnabled = (step) => {
    const owner = step.loopOwnerId || step.holdOwnerId || step.id; // "Repeat" + "End repeat" switch together
    const value = !step.enabled;
    setSteps((prev) => prev.map((s) => (
      s.id === owner || s.loopOwnerId === owner || s.holdOwnerId === owner ? { ...s, enabled: value } : s
    )));
  };

  const updateStep = (id, patch) => {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  };

  const setKeyMode = (step, mode) => {
    setSteps((prev) => {
      const cleaned = prev.filter((item) => item.holdOwnerId !== step.id);
      const index = cleaned.findIndex((item) => item.id === step.id);
      if (index < 0) return prev;
      cleaned[index] = { ...cleaned[index], keyMode: mode };
      if (mode !== 'hold') return cleaned;

      const duration = formatDelay(step.holdDuration || '0,50');
      cleaned.splice(index + 1, 0,
        {
          id: `${step.id}-hold-delay`, enabled: step.enabled, type: 'delay',
          duration, randomize: false, variance: '0', holdOwnerId: step.id,
        },
        {
          id: `${step.id}-hold-release`, enabled: step.enabled, type: 'key',
          keyName: step.keyName, keyMode: 'release', holdOwnerId: step.id,
        },
      );
      return cleaned;
    });
  };

  const duplicateStep = (step) => {
    const copy = {
      ...step,
      id: `step-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    };
    const idx = steps.findIndex((s) => s.id === step.id);
    const updated = [...steps];
    updated.splice(idx + 1, 0, copy);
    setSteps(updated);
    showToast(`Step #${idx + 1} duplicated`);
  };

  const deleteStep = (id) => {
    setSteps((prev) => {
      const ownerId = prev.find((s) => s.id === id)?.loopOwnerId || id; // "End repeat" removes the whole block
      return prev.filter((s) => s.id !== id && s.id !== ownerId && s.loopOwnerId !== ownerId && s.holdOwnerId !== id);
    });
  };

  const reorderSteps = (sourceId, targetId, position) => {
    if (!sourceId || sourceId === targetId) return;
    setSteps((prev) => {
      const sourceIndex = prev.findIndex((step) => step.id === sourceId);
      const targetIndex = prev.findIndex((step) => step.id === targetId);
      if (sourceIndex < 0 || targetIndex < 0) return prev;
      const next = [...prev];
      const [moved] = next.splice(sourceIndex, 1);
      const insertionIndex = targetIndex + (position === 'after' ? 1 : 0) - (sourceIndex < targetIndex ? 1 : 0);
      next.splice(insertionIndex, 0, moved);
      return next;
    });
  };

  const simulateCoordinatePick = (id) => {
    setPickingStepId(id);
    if (nativeReady && window.notafkBridge) {
      window.notafkBridge.pickCoordinate(id, backgroundEnabled && target ? target.hwnd : null);
      return;
    }
    setTimeout(() => {
      const randomX = Math.floor(Math.random() * 1600) + 160;
      const randomY = Math.floor(Math.random() * 800) + 120;
      updateStep(id, { coords: { x: randomX, y: randomY, picked: true } });
      setPickingStepId(null);
      pushLog(`Picked screen coords X:${randomX}, Y:${randomY}`, 'ready');
      showToast(`Picked X:${randomX}, Y:${randomY}`);
    }, 650);
  };

  // Parse comma/dot numbers for validation check
  const parseNum = (val) => parseFloat(String(val).replace(',', '.')) || 0;
  const formatDelay = (value) => {
    const numericValue = parseFloat(String(value).replace(',', '.'));
    return Number.isFinite(numericValue)
      ? Number(numericValue.toFixed(2)).toString().replace('.', ',')
      : value;
  };
  const isMinGreaterThanMax = parseNum(minDelay) > parseNum(maxDelay);

  const swapMinMax = () => {
    const temp = minDelay;
    setMinDelay(maxDelay);
    setMaxDelay(temp);
    showToast('Min and max swapped');
  };

  const totalTargetCycles =
    runMode === 'once' ? 1 : runMode === 'repeat' ? repeatCount || 0 : '∞';

  const numericJitter = parseInt(String(targetJitter).replace(/\D/g, ''), 10) || 3;

  // Preview of the path shape: an S-curve plus small wobbles, both growing with the irregularity %
  const irregularPath = (() => {
    const a = Number(curvePercent) / 100;
    const pts = [];
    for (let i = 0; i <= 60; i += 1) {
      const t = i / 60;
      const env = Math.sin(Math.PI * t);
      const off = a * (13 * Math.sin(2 * Math.PI * t)
        + env * (3.2 * Math.sin(9 * Math.PI * t + 0.7) + 1.8 * Math.sin(17 * Math.PI * t + 1.9)));
      // offset along the normal of the base line (16,40) -> (220,16)
      pts.push(`${(16 + 204 * t + off * 0.117).toFixed(1)} ${(40 - 24 * t + off * 0.993).toFixed(1)}`);
    }
    return `M ${pts.join(' L ')}`;
  })();

  return (
    <div className="app-shell h-screen w-full text-slate-200 flex items-center justify-center font-sans select-none relative overflow-hidden">
      {nativeReady && RESIZE_EDGES.map(([pos, edges]) => (
        <div
          key={edges}
          className={`resize-edge absolute z-[60] ${pos}`}
          onPointerDown={(e) => { if (e.button === 0) window.notafkBridge?.startResize(edges); }}
        />
      ))}

      {/* Toast Notification */}
      {countdown !== null && (
        <div
          className="fixed inset-0 z-[80] flex flex-col items-center justify-center bg-black/65 backdrop-blur-[2px] cursor-pointer"
          onClick={toggleRecording}
        >
          <div key={countdown} className="text-[132px] leading-none font-bold text-white tabular-nums animate-pulse">{countdown}</div>
          <div className="mt-4 flex items-center gap-2 text-sm text-slate-300">
            <Circle className="w-3 h-3 text-red-400 fill-current" />
            Recording starts. NotAFK will minimize. Click to cancel.
          </div>
        </div>
      )}

      {dialog && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/55 backdrop-blur-[2px]"
          onPointerDown={(e) => { if (e.target === e.currentTarget) setDialog(null); }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (dialog.kind === 'rename') renameMacro(dialog.name, dialog.value);
              else deleteMacro(dialog.name);
            }}
            onKeyDown={(e) => { if (e.key === 'Escape') setDialog(null); }}
            className="w-[340px] rounded-xl bg-[#13161f] border border-[#2c344a] shadow-[0_20px_60px_rgba(0,0,0,0.7)] p-4 space-y-3"
          >
            <div className="flex items-center gap-2">
              {dialog.kind === 'rename'
                ? <Pencil className="w-3.5 h-3.5 text-blue-400" />
                : <AlertTriangle className="w-3.5 h-3.5 text-red-400" />}
              <h3 className={`text-[11px] font-bold uppercase tracking-wider ${dialog.kind === 'rename' ? 'text-[#38bdf8]' : 'text-red-300'}`}>
                {dialog.kind === 'rename' ? 'Rename Automation' : 'Delete Automation'}
              </h3>
            </div>
            {dialog.kind === 'rename' ? (
              <input
                autoFocus
                value={dialog.value}
                onChange={(e) => setDialog({ ...dialog, value: e.target.value })}
                onFocus={(e) => e.target.select()}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-[#252b3d] focus:border-[#0A84FF] text-xs text-slate-200 font-medium outline-none select-text"
              />
            ) : (
              <p className="text-xs text-slate-300">
                Delete <span className="font-semibold text-white">"{dialog.name}"</span>? This cannot be undone.
              </p>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setDialog(null)}
                className="px-3 py-1.5 rounded-lg bg-[#1b202e] hover:bg-[#242b3d] border border-[#2c344a] text-[11px] font-medium text-slate-300 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                autoFocus={dialog.kind === 'delete'}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg border text-[11px] font-semibold transition-colors ${
                  dialog.kind === 'rename'
                    ? 'bg-[#0A84FF] hover:bg-[#2b95ff] border-[#0A84FF] text-white'
                    : 'bg-red-500/15 hover:bg-red-500/25 border-red-500/40 text-red-300'
                }`}
              >
                {dialog.kind === 'rename' ? <Check className="w-3 h-3" /> : <Trash2 className="w-3 h-3" />}
                <span>{dialog.kind === 'rename' ? 'Save' : 'Delete'}</span>
              </button>
            </div>
          </form>
        </div>
      )}

      {showSettings && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/55 backdrop-blur-[2px]"
          onPointerDown={(e) => { if (e.target === e.currentTarget) setShowSettings(false); }}
        >
          <div className="w-[340px] rounded-xl bg-[#13161f] border border-[#2c344a] shadow-[0_20px_60px_rgba(0,0,0,0.7)] p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Settings className="w-3.5 h-3.5 text-blue-400" />
              <h3 className="text-[11px] font-bold uppercase tracking-wider text-[#38bdf8]">Settings</h3>
            </div>
            {[['hotkeyStart', 'Start hotkey'], ['hotkeyStop', 'Stop hotkey']].map(([key, label]) => (
              <label key={key} className="flex items-center justify-between text-xs text-slate-300">
                <span>{label}</span>
                <select
                  value={prefs[key]}
                  onChange={(e) => {
                    const other = key === 'hotkeyStart' ? 'hotkeyStop' : 'hotkeyStart';
                    const value = e.target.value; // picking the other key's value swaps them
                    setPrefs((p) => ({ ...p, [key]: value, ...(p[other] === value ? { [other]: p[key] } : {}) }));
                  }}
                  className="bg-[#0b0d12] border border-[#2c3244] rounded-lg px-2 py-1 text-[11px] text-slate-200 outline-none"
                >
                  {F_KEYS.map((k) => <option key={k}>{k}</option>)}
                </select>
              </label>
            ))}
            <p className="text-[10px] text-slate-500">Esc always stops a run or a recording.</p>
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.minimizeOnStart}
                onChange={(e) => setPrefs((p) => ({ ...p, minimizeOnStart: e.target.checked }))}
                className="accent-[#0A84FF]"
              />
              Minimize NotAFK while an automation runs
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.askAdmin}
                onChange={(e) => setPrefs((p) => ({ ...p, askAdmin: e.target.checked }))}
                className="accent-[#0A84FF]"
              />
              Suggest administrator mode at startup
            </label>
            {appInfo && !appInfo.admin && (
              <button
                type="button"
                onClick={() => { setShowSettings(false); restartAsAdmin(); }}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#181c26] hover:bg-[#1f2533] border border-[#2c3244] text-[11px] font-semibold text-slate-200"
              >
                <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
                Restart as administrator
              </button>
            )}
            {appInfo?.updates && (
              <>
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={prefs.checkUpdates}
                    onChange={(e) => setPrefs((p) => ({ ...p, checkUpdates: e.target.checked }))}
                    className="accent-[#0A84FF]"
                  />
                  Check for updates at startup
                </label>
                <button
                  type="button"
                  onClick={() => checkForUpdate(true)}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#181c26] hover:bg-[#1f2533] border border-[#2c3244] text-[11px] font-semibold text-slate-200"
                >
                  <Download className="w-3.5 h-3.5 text-blue-400" />
                  Check for updates now
                </button>
              </>
            )}
            {appInfo && (
              <p className="text-[10px] text-slate-500">
                NotAFK {appInfo.version}{appInfo.admin ? ' · running as administrator' : ''}
              </p>
            )}
            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={() => setShowSettings(false)}
                className="px-3 py-1.5 rounded-lg bg-[#0A84FF] hover:bg-[#2b95ff] border border-[#0A84FF] text-[11px] font-semibold text-white"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {adminPrompt && (
        <div className="fixed inset-0 z-[75] flex items-center justify-center bg-black/55 backdrop-blur-[2px]">
          <div className="w-[380px] rounded-xl bg-[#13161f] border border-[#2c344a] shadow-[0_20px_60px_rgba(0,0,0,0.7)] p-4 space-y-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              <h3 className="text-[11px] font-bold uppercase tracking-wider text-[#38bdf8]">Run as administrator?</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Windows blocks clicks and keys sent to apps that run as administrator (Task Manager, installers,
              some games) unless NotAFK runs as administrator too.
            </p>
            <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
              <input type="checkbox" checked={adminDontAsk} onChange={(e) => setAdminDontAsk(e.target.checked)} className="accent-[#0A84FF]" />
              Don't ask again
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => {
                  setAdminPrompt(false);
                  if (adminDontAsk) setPrefs((p) => ({ ...p, askAdmin: false }));
                }}
                className="px-3 py-1.5 rounded-lg bg-[#181c26] hover:bg-[#1f2533] border border-[#2c3244] text-[11px] font-semibold text-slate-300"
              >
                Not now
              </button>
              <button
                type="button"
                onClick={() => {
                  if (adminDontAsk) setPrefs((p) => ({ ...p, askAdmin: false }));
                  restartAsAdmin();
                }}
                className="px-3 py-1.5 rounded-lg bg-[#0A84FF] hover:bg-[#2b95ff] border border-[#0A84FF] text-[11px] font-semibold text-white"
              >
                Restart as admin
              </button>
            </div>
          </div>
        </div>
      )}

      {update && !adminPrompt && (
        <div className="fixed inset-0 z-[75] flex items-center justify-center bg-black/55 backdrop-blur-[2px]">
          <div className="w-[400px] rounded-xl bg-[#13161f] border border-[#2c344a] shadow-[0_20px_60px_rgba(0,0,0,0.7)] p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Download className="w-3.5 h-3.5 text-blue-400" />
              <h3 className="text-[11px] font-bold uppercase tracking-wider text-[#38bdf8]">Update available</h3>
            </div>
            <p className="text-xs text-slate-300">
              NotAFK {update.version} is available (you have {update.current}).
              {update.canInstall ? ' NotAFK closes, updates and opens again; your automations stay.' : ' Updates install in the built app only.'}
            </p>
            {update.notes && (
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-[10px] text-slate-400 bg-[#0b0d12] border border-[#2c3244] rounded-lg p-2 font-sans">
                {update.notes}
              </pre>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                disabled={updating}
                onClick={() => setUpdate(null)}
                className="px-3 py-1.5 rounded-lg bg-[#181c26] hover:bg-[#1f2533] border border-[#2c3244] text-[11px] font-semibold text-slate-300 disabled:opacity-50"
              >
                Later
              </button>
              {update.canInstall && (
                <button
                  type="button"
                  disabled={updating}
                  onClick={installUpdate}
                  className="px-3 py-1.5 rounded-lg bg-[#0A84FF] hover:bg-[#2b95ff] border border-[#0A84FF] text-[11px] font-semibold text-white disabled:opacity-60"
                >
                  {updating ? 'Downloading…' : 'Update now'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[90] flex items-center gap-2 px-4 py-2 rounded-xl bg-[#181c26]/95 border border-blue-500/40 text-xs font-medium text-blue-100 shadow-2xl backdrop-blur-md">
          <Sparkles className="w-3.5 h-3.5 text-blue-400" />
          <span>{toast}</span>
        </div>
      )}

      {/* 16:9 application container */}
      <div
        className="app-card relative w-full h-full bg-[#0d0f14] border border-[#222634] rounded-2xl overflow-hidden flex flex-col"
      >
        {/* 1. TOP FRAMELESS WINDOW TITLEBAR */}
        <div
          onMouseDown={(e) => { if (e.button === 0 && !e.target.closest('button')) window.notafkBridge?.startDrag(); }}
          onDoubleClick={(e) => { if (!e.target.closest('button')) window.notafkBridge?.toggleMaximize(); }}
          className="h-9 shrink-0 bg-[#090b0f] border-b border-[#1a1e29] px-4 flex items-center justify-between"
        >
          <div className="flex items-center gap-2.5">
            <span className="text-[11px] font-bold tracking-[0.2em] text-slate-200">
              NotAFK
            </span>
            <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-md bg-[#151a24] text-blue-300 border border-[#2c344a]">
              v1.0
            </span>
          </div>

          {/* Window Controls */}
          <div className="flex items-center gap-1">
            <button onClick={() => setShowSettings(true)} title="Settings" className="w-6 h-6 rounded hover:bg-white/5 flex items-center justify-center text-slate-400 hover:text-slate-200">
              <Settings className="w-3 h-3" />
            </button>
            <button onClick={() => window.notafkBridge?.minimizeWindow()} className="w-6 h-6 rounded hover:bg-white/5 flex items-center justify-center text-slate-400 hover:text-slate-200">
              <Minus className="w-3 h-3" />
            </button>
            <button onClick={() => window.notafkBridge?.toggleMaximize()} className="w-6 h-6 rounded hover:bg-white/5 flex items-center justify-center text-slate-400 hover:text-slate-200">
              <Maximize2 className="w-2.5 h-2.5" />
            </button>
            <button onClick={() => window.notafkBridge?.closeWindow()} className="w-6 h-6 rounded hover:bg-red-500/20 flex items-center justify-center text-slate-400 hover:text-red-400">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* 2. TOP MASTER CONTROL HEADER */}
        <div className="relative h-14 shrink-0 px-4 bg-[#12151e] border-b border-[#1e2330] flex items-center justify-between gap-4">
          {/* Left: Record + time limit */}
          <div className="flex items-center gap-2">
            <button
              onClick={toggleRecording}
              disabled={isRunning}
              title={isRecording ? `Finish recording (${prefs.hotkeyStop} / Esc)` : 'Record your clicks and typing as steps'}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-colors ${
                isRecording
                  ? 'bg-red-500/20 border-red-400/50 text-red-200'
                  : 'bg-[#0d0f14] hover:bg-[#161a25] border-[#222838] text-slate-300 disabled:opacity-40'
              }`}
            >
              <Circle className={`w-3 h-3 text-red-400 ${isRecording ? 'fill-current animate-pulse' : ''}`} />
              <span>{isRecording ? 'Stop recording' : countdown !== null ? `Starting in ${countdown}` : 'Record'}</span>
            </button>
            <label
              title="Stop the run automatically after this many minutes (empty = no limit)"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-[#0d0f14] border border-[#222838] text-xs text-slate-400"
            >
              <Timer className="w-3.5 h-3.5 text-amber-400" />
              <span>Stop after</span>
              <input
                type="text"
                inputMode="numeric"
                aria-label="Time limit in minutes"
                value={timeLimit}
                placeholder="-"
                onChange={(e) => setTimeLimit(e.target.value.replace(/[^0-9]/g, '').slice(0, 4))}
                className="w-8 bg-transparent text-right font-mono text-slate-200 outline-none placeholder:text-slate-600"
              />
              <span>min</span>
            </label>
          </div>

          {/* Center: Primary Start (F6) & Stop (F7 / Esc) Controls */}
          <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-3">
            <button
              onClick={handleStart}
              disabled={isRunning}
              className={`flex items-center gap-2 px-6 py-2 rounded-xl font-semibold text-xs tracking-wide transition-all ${
                isRunning
                  ? 'bg-[#0A84FF]/25 text-blue-200 border border-blue-400/40 cursor-not-allowed'
                  : 'bg-gradient-to-b from-[#1e90ff] to-[#006be0] hover:from-[#389bff] hover:to-[#0A84FF] text-white shadow-[0_0_24px_rgba(10,132,255,0.45)] active:scale-95 border border-blue-400/30'
              }`}
            >
              <Play className={`w-3.5 h-3.5 fill-current ${isRunning ? 'animate-ping' : ''}`} />
              <span>Start ({prefs.hotkeyStart})</span>
            </button>

            <button
              onClick={handleStop}
              className={`flex items-center gap-2 px-5 py-2 rounded-xl font-semibold text-xs tracking-wide transition-all border ${
                isRunning
                  ? 'bg-gradient-to-b from-[#ff564d] to-[#e0352b] text-white border-red-400/40 shadow-[0_0_22px_rgba(255,69,58,0.5)] active:scale-95'
                  : 'bg-[#26191d] hover:bg-[#ff453a] text-red-300 hover:text-white border-red-500/30'
              }`}
            >
              <Square className="w-3 h-3 fill-current" />
              <span>Stop ({prefs.hotkeyStop} / Esc)</span>
            </button>
          </div>

          {/* Right: Live Status & Cycles Pill */}
          <div className="flex items-center gap-2.5">
            <div
              className={`px-3 py-1.5 rounded-xl border flex items-center gap-2 text-xs font-semibold ${
                isRunning
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                  : 'bg-[#0d0f14] border-[#222838] text-[#38bdf8]'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  isRunning ? 'bg-emerald-400 animate-ping' : 'bg-[#38bdf8]'
                }`}
              />
              <span>Status: {isRunning ? 'Running' : 'Ready'}</span>
            </div>

            <div className="px-3 py-1.5 rounded-xl bg-[#0d0f14] border border-[#222838] flex items-center gap-2 text-xs">
              <span className="text-slate-400">Cycles:</span>
              <span className="font-mono font-bold text-slate-200">
                {currentCycle} / {totalTargetCycles}
              </span>
            </div>
          </div>
        </div>

        {/* 3. SYMMETRIC 3-COLUMN 16:9 SPLIT WORKSPACE (LEFT MENU | CENTER TIMELINE | RIGHT MENU) */}
        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-3.5 p-3.5 bg-[#0d0f14] overflow-hidden">
          
          {/* ================= LEFT SIDEBAR MENU (3 COLS) ================= */}
          <div className="left-col lg:col-span-3 flex flex-col gap-3 min-h-0 overflow-hidden">
            
            {/* LEFT CARD 1: Macro Profile Manager */}
            <div className="rounded-xl bg-[#13161f] border border-[#1e2332] p-3.5 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-[#38bdf8]">
                  Saved Automations
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => setDialog({ kind: 'rename', name: selectedMacro, value: selectedMacro })}
                    title="Rename"
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#1b202e] hover:bg-[#242b3d] border border-[#2c344a] text-[11px] font-medium text-slate-200 transition-colors"
                  >
                    <Pencil className="w-3 h-3 text-blue-400" />
                  </button>
                  <button
                    onClick={() => {
                      setSavedMacros((current) => ({ ...current, [selectedMacro]: { steps, settings: currentSettings() } }));
                      setRecentMacros((current) => [{ id: `saved-${selectedMacro}`, name: selectedMacro, tag: 'Saved' }, ...current.filter((item) => item.name !== selectedMacro)].slice(0, 3));
                      showToast(`"${selectedMacro}" saved`);
                    }}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#1b202e] hover:bg-[#242b3d] border border-[#2c344a] text-[11px] font-medium text-slate-200 transition-colors"
                  >
                    <Save className="w-3 h-3 text-cyan-400" />
                    <span>Save</span>
                  </button>
                  <button
                    onClick={importAutomation}
                    title="Import from file"
                    className="p-1.5 rounded-lg bg-[#1b202e] hover:bg-[#242b3d] border border-[#2c344a] text-slate-300 transition-colors"
                  >
                    <Upload className="w-3 h-3" />
                  </button>
                  <button
                    onClick={exportAutomation}
                    title="Export to file"
                    className="p-1.5 rounded-lg bg-[#1b202e] hover:bg-[#242b3d] border border-[#2c344a] text-slate-300 transition-colors"
                  >
                    <Download className="w-3 h-3" />
                  </button>
                </div>
              </div>

              {/* Dropdown Select Saved Macro */}
              <div className="relative">
                <button
                  onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                  className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] hover:bg-[#0f1219] border border-[#252b3d] text-xs text-left flex items-center justify-between transition-colors"
                >
                  <span className="text-slate-200 font-medium truncate">
                    {selectedMacro || 'Select automation'}
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                </button>

                {isDropdownOpen && (
                  <div className="absolute left-0 right-0 mt-1 rounded-xl bg-[#161a25] border border-[#2c3246] shadow-2xl py-1 z-40">
                    <button
                      onClick={() => {
                        setSteps([]);
                        setSelectedMacro('New Automation');
                        setIsDropdownOpen(false);
                        showToast('New automation');
                      }}
                      className="w-full px-3 py-2 text-xs text-left hover:bg-blue-500/15 flex items-center gap-2 text-slate-200"
                    >
                      <Plus className="w-3.5 h-3.5 text-blue-400" />
                      <span>Create New</span>
                    </button>
                    {Object.keys(savedMacros).map((name) => (
                      <div
                        key={name}
                        onClick={() => {
                          loadAutomation(name);
                          setIsDropdownOpen(false);
                          pushLog(`Loaded profile "${name}"`, 'ready');
                        }}
                        className="w-full px-3 py-2 text-xs text-left hover:bg-blue-500/15 flex items-center gap-2 text-slate-300 cursor-pointer"
                      >
                        <FolderOpen className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                        <span className="truncate flex-1">{name}</span>
                        <button
                          type="button"
                          title="Delete"
                          onClick={(e) => { e.stopPropagation(); setIsDropdownOpen(false); setDialog({ kind: 'delete', name }); }}
                          className="w-5 h-5 shrink-0 rounded flex items-center justify-center text-slate-500 hover:text-red-400 hover:bg-red-500/15"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Recently used macros */}
              <div className="space-y-1 pt-0.5">
                <div className="px-1 pb-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Recently used
                </div>
                {recentMacros.length === 0 && (
                  <div className="px-2.5 py-1.5 text-[11px] text-slate-500">No saved automations yet</div>
                )}
                {recentMacros.map((preset) => (
                  <div
                    key={preset.id}
                    onClick={() => {
                      if (savedMacros[preset.name]) loadAutomation(preset.name);
                      else setSelectedMacro(preset.name);
                      setRecentMacros((current) => [preset, ...current.filter((item) => item.id !== preset.id)].slice(0, 3));
                      pushLog(`Loaded profile "${preset.name}"`, 'ready');
                      showToast(`Loaded "${preset.name}"`);
                    }}
                    className={`w-full px-2.5 py-1.5 rounded-lg text-left text-[11px] flex items-center gap-2 border transition-all cursor-pointer ${
                      selectedMacro === preset.name
                        ? 'bg-[#17253b] border-[#264773] text-blue-200'
                        : 'bg-[#0e1017] hover:bg-[#141822] border-[#1c202e] text-slate-400'
                    }`}
                  >
                    <span className="truncate font-medium flex-1">{preset.name}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#090b10] text-slate-400">
                      {preset.tag}
                    </span>
                    <button
                      type="button"
                      title="Delete"
                      onClick={(e) => { e.stopPropagation(); setDialog({ kind: 'delete', name: preset.name }); }}
                      className="w-5 h-5 shrink-0 rounded flex items-center justify-center text-slate-500 hover:text-red-400 hover:bg-red-500/15"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* LEFT CARD 2: Action Palette */}
            <div className="rounded-xl bg-[#13161f] border border-[#1e2332] p-3.5 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-[#38bdf8]">
                  Action Palette
                </span>
                <span className="text-[10px] text-slate-500">Insert Step</span>
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                {PALETTE.map(([type, label, Icon, color]) => (
                  <button
                    key={type}
                    onClick={() => addStep(type)}
                    className="group flex items-center gap-2 px-2.5 py-2 rounded-lg bg-[#0e1118] hover:bg-[#171c28] border border-[#22283a] hover:border-blue-500/40 transition-all active:scale-95 text-left"
                  >
                    <Icon className={`w-3.5 h-3.5 shrink-0 ${color}`} />
                    <span className="text-xs font-semibold text-slate-200 truncate">+ Add {label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* LEFT CARD 3: Run Mode (Moved to Left Menu for balanced left/right layout) */}
            <div className="rounded-xl bg-[#13161f] border border-[#1e2332] p-3.5 space-y-2.5 mt-auto">
              <div className="flex items-center gap-2">
                <Repeat className="w-3.5 h-3.5 text-[#38bdf8]" />
                <h3 className="text-xs font-bold text-[#38bdf8] tracking-wide">Run Mode</h3>
              </div>

              <div className="space-y-2 text-xs">
                <label
                  onClick={() => setRunMode('once')}
                  className="flex items-center gap-2.5 cursor-pointer py-1 px-2 rounded-lg hover:bg-white/5"
                >
                  <div
                    className={`w-4 h-4 rounded-full border flex items-center justify-center ${
                      runMode === 'once'
                        ? 'border-[#0A84FF] bg-[#0A84FF]/20'
                        : 'border-slate-500'
                    }`}
                  >
                    {runMode === 'once' && (
                      <div className="w-2 h-2 rounded-full bg-[#0A84FF]" />
                    )}
                  </div>
                  <span className="text-slate-200">Run once</span>
                </label>

                <div
                  onClick={() => setRunMode('repeat')}
                  className="flex items-center justify-between cursor-pointer py-1 px-2 rounded-lg hover:bg-white/5"
                >
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`w-4 h-4 rounded-full border flex items-center justify-center ${
                        runMode === 'repeat'
                          ? 'border-[#0A84FF] bg-[#0A84FF]/20'
                          : 'border-slate-500'
                      }`}
                    >
                      {runMode === 'repeat' && (
                        <div className="w-2 h-2 rounded-full bg-[#0A84FF]" />
                      )}
                    </div>
                    <span className="text-slate-200">Repeat:</span>
                  </div>

                  <div className="flex items-center bg-[#0b0d12] border border-[#282e40] rounded-lg px-2 py-1">
                    <input
                      type="text"
                      inputMode="numeric"
                      value={repeatCount}
                      onChange={(e) => setRepeatCount(e.target.value.replace(/\D/g, ''))}
                      className="w-9 bg-transparent text-right font-mono text-xs text-white outline-none"
                    />
                    <span className="text-slate-400 ml-1">times</span>
                  </div>
                </div>

                <label
                  onClick={() => setRunMode('loop')}
                  className="flex items-center gap-2.5 cursor-pointer py-1 px-2 rounded-lg hover:bg-white/5"
                >
                  <div
                    className={`w-4 h-4 rounded-full border flex items-center justify-center ${
                      runMode === 'loop'
                        ? 'border-[#0A84FF] bg-[#0A84FF]/20'
                        : 'border-slate-500'
                    }`}
                  >
                    {runMode === 'loop' && (
                      <div className="w-2 h-2 rounded-full bg-[#0A84FF]" />
                    )}
                  </div>
                  <span className="text-slate-200">Loop until stopped</span>
                </label>
              </div>
            </div>
          </div>

          {/* ================= CENTER WORKSPACE: ACTION TIMELINE (6 COLS) ================= */}
          <div className="lg:col-span-6 flex flex-col min-h-0 rounded-xl bg-[#11141c] border border-[#1e2332] overflow-hidden">
            
            {/* Center Timeline Header */}
            <div className="px-4 py-2.5 bg-[#141822] border-b border-[#1f2434] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
                  Action Timeline
                </span>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-[#0c0e14] text-blue-400 border border-[#23293a]">
                  {steps.filter((s) => s.enabled).length} / {steps.length} Enabled
                </span>
                <span className="hidden sm:inline text-[11px] text-slate-400">
                  Est. Cycle:{' '}
                  <strong className="text-slate-200 font-mono">
                    {(
                      steps.filter((step) => step.enabled).length * 0.62 +
                      (globalDelayEnabled
                        ? Math.max(0, steps.filter((step) => step.enabled).length - 1) *
                          ((parseNum(minDelay) + parseNum(maxDelay)) / 2)
                        : 0)
                    ).toFixed(2)}s
                  </strong>
                </span>
              </div>

              <button
                onClick={() => {
                  setSteps([]);
                  pushLog('Cleared all steps from timeline', 'warn');
                  showToast('All steps cleared');
                }}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#1b1f2c] hover:bg-[#2a191f] border border-[#2a3042] hover:border-red-500/30 text-[11px] font-medium text-slate-300 hover:text-red-300 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                <span>Clear All Steps</span>
              </button>
            </div>

            {/* Scrollable Step Sequencer List */}
            <div className="flex-1 min-h-0 p-3 overflow-y-auto flex flex-col gap-4">
              {steps.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-6">
                  <div className="w-11 h-11 rounded-2xl bg-[#161a25] border border-[#24293a] flex items-center justify-center text-slate-500 mb-2.5">
                    <Sliders className="w-5 h-5" />
                  </div>
                  <p className="text-xs font-semibold text-slate-300">
                    No steps yet
                  </p>
                  <p className="text-[11px] text-slate-500 mt-1 max-w-xs">
                    Add steps from the <span className="text-blue-400">Action Palette</span> on the left, or press Record.
                  </p>
                </div>
              ) : (
                steps.map((step, index) => {
                  const isCurrentlyExecuting = activeStepIndex === index && isRunning;
                  // indent steps inside repeat blocks
                  const depth = steps.slice(0, index).reduce((d, s) => d + (s.type === 'loop') - (s.type === 'loopEnd'), 0)
                    - (step.type === 'loopEnd' ? 1 : 0);
                  return (
                    <div
                      key={step.id}
                      data-step-id={step.id}
                      style={{ marginLeft: Math.max(0, depth) * 20 }}
                      className={`group relative rounded-xl p-2.5 transition-all duration-150 border flex flex-wrap xl:flex-nowrap items-center justify-between gap-2.5 cursor-grab active:cursor-grabbing ${
                        draggedStepId === step.id ? 'scale-[0.99] ring-2 ring-[#38bdf8]/80' : ''
                      } ${
                        dropTarget?.id === step.id && dropTarget.position === 'before'
                          ? 'mt-8'
                          : dropTarget?.id === step.id && dropTarget.position === 'after'
                            ? 'mb-8'
                            : ''
                      } ${
                        isCurrentlyExecuting
                          ? 'bg-[#182338] border-[#0A84FF] shadow-[0_0_18px_rgba(10,132,255,0.28)]'
                        : step.enabled
                          ? 'bg-[#161a25] hover:bg-[#191e2b] border-[#252b3d]'
                          : 'bg-[#0e1017]/60 border-[#1a1e2a] opacity-50'
                      }`}
                    >
                      {dropTarget?.id === step.id && (
                        <div className={`pointer-events-none absolute left-2 right-2 z-20 h-0.5 rounded-full bg-[#38bdf8] shadow-[0_0_8px_rgba(56,189,248,0.9)] ${dropTarget.position === 'before' ? '-top-6' : '-bottom-6'}`} />
                      )}
                      {/* Step Controls Row */}
                      <div className="flex flex-wrap items-center gap-2 flex-1 min-w-0">
                        {/* Checkbox "On" */}
                        <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                          <button
                            type="button"
                            onClick={() => toggleEnabled(step)}
                            className={`w-4 h-4 rounded flex items-center justify-center transition-colors ${
                              step.enabled
                                ? 'bg-[#0A84FF] text-white'
                                : 'bg-[#0b0d12] border border-[#32384c] text-transparent'
                            }`}
                          >
                            <Check className="w-3 h-3 stroke-[3]" />
                          </button>
                          <span className="text-[11px] text-slate-300 font-medium">On</span>
                        </label>

                        {/* Vertical-style #1 Badge matching reference screenshot */}
                        <div
                          className={`px-2 py-1.5 rounded-lg text-[11px] font-mono font-bold border shrink-0 ${
                            isCurrentlyExecuting
                              ? 'bg-blue-500 text-white border-blue-300'
                              : 'bg-[#15263c] text-[#4da3ff] border-[#24436b]'
                          }`}
                        >
                          #{index + 1}
                        </div>

                        {/* CLICK STEP */}
                        {step.type === 'click' && (
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1 font-semibold text-white">
                              <MousePointer className="w-3.5 h-3.5 text-blue-400" />
                              <span>Click</span>
                            </div>

                            <button
                              onClick={() => simulateCoordinatePick(step.id)}
                              className={`flex items-center gap-1 px-2 py-1 rounded-lg font-medium border transition-all ${
                                pickingStepId === step.id
                                  ? 'bg-amber-500/20 text-amber-300 border-amber-400/50 animate-pulse'
                                  : 'bg-[#14283c] hover:bg-[#1b3550] text-[#38bdf8] border-[#23476b]'
                              }`}
                            >
                              <Crosshair className="w-3 h-3" />
                              <span>
                                {pickingStepId === step.id
                                  ? 'Pick...'
                                  : step.coords.picked
                                  ? `${step.coords.x},${step.coords.y}`
                                  : 'Select'}
                              </span>
                            </button>

                            <select
                              value={step.button}
                              onChange={(e) => updateStep(step.id, { button: e.target.value })}
                              className="bg-[#0b0d12] border border-[#2c3244] rounded-lg px-2 py-1 text-[11px] text-slate-200 outline-none"
                            >
                              <option value="Left click">Left click</option>
                              <option value="Right click">Right click</option>
                              <option value="Middle click">Middle click</option>
                              <option value="Double click">Double click</option>
                            </select>
                            <label className="flex items-center gap-1 text-slate-400">
                              Times
                              <input
                                type="text"
                                inputMode="numeric"
                                aria-label="Number of clicks"
                                value={step.times ?? '1'}
                                onChange={(e) => updateStep(step.id, { times: e.target.value.replace(/[^0-9]/g, '') })}
                                onBlur={() => updateStep(step.id, { times: String(Math.max(1, parseInt(step.times, 10) || 1)) })}
                                className="w-10 bg-[#0b0d12] border border-[#2c3244] rounded-md px-1.5 py-1 text-center font-mono text-[11px] text-slate-200 outline-none"
                              />
                            </label>
                            <label
                              className="flex items-center gap-1 text-slate-400"
                              title="Keep the button pressed this long (0 = normal click)"
                            >
                              Hold
                              <input
                                type="text"
                                inputMode="decimal"
                                aria-label="Hold the button in seconds"
                                value={step.holdTime ?? '0'}
                                onChange={(e) => updateStep(step.id, { holdTime: e.target.value.replace(/[^0-9,.]/g, '') })}
                                onBlur={() => updateStep(step.id, { holdTime: formatDelay(step.holdTime || '0') })}
                                className="w-10 bg-[#0b0d12] border border-[#2c3244] rounded-md px-1.5 py-1 text-center font-mono text-[11px] text-slate-200 outline-none"
                              />
                              <span>s</span>
                            </label>
                            {Number(step.times) > 1 && (
                              <label className="flex items-center gap-1 text-slate-400">
                                Interval
                                <input
                                  type="text"
                                  inputMode="decimal"
                                  aria-label="Interval between clicks in seconds"
                                  value={step.clickInterval ?? '0,10'}
                                  onChange={(e) => updateStep(step.id, { clickInterval: e.target.value.replace(/[^0-9,.]/g, '') })}
                                  onBlur={() => updateStep(step.id, { clickInterval: formatDelay(step.clickInterval ?? '0,10') })}
                                  className="w-12 bg-[#0b0d12] border border-[#2c3244] rounded-md px-1.5 py-1 text-center font-mono text-[11px] text-slate-200 outline-none"
                                />
                                <span>s</span>
                              </label>
                            )}
                          </div>
                        )}

                        {/* MOVE STEP */}
                        {step.type === 'move' && (
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1 font-semibold text-white">
                              <Move className="w-3.5 h-3.5 text-cyan-400" />
                              <span>Move</span>
                            </div>

                            <button
                              onClick={() => simulateCoordinatePick(step.id)}
                              className="flex items-center gap-1 px-2 py-1 rounded-lg font-medium bg-[#14283c] hover:bg-[#1b3550] text-[#38bdf8] border border-[#23476b]"
                            >
                              <Crosshair className="w-3 h-3" />
                              <span>
                                {pickingStepId === step.id
                                  ? 'Pick...'
                                  : `X:${step.coords.x} Y:${step.coords.y}`}
                              </span>
                            </button>

                          </div>
                        )}

                        {/* TEXT STEP */}
                        {step.type === 'text' && (
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1 font-semibold text-white">
                              <Keyboard className="w-3.5 h-3.5 text-purple-400" />
                              <span>Text</span>
                            </div>

                            <input
                              type="text"
                              value={step.textValue}
                              onChange={(e) => updateStep(step.id, { textValue: e.target.value })}
                              className="w-36 bg-[#0b0d12] border border-[#2c3244] rounded-md px-2 py-1 font-mono text-[11px] text-purple-200 outline-none"
                            />

                            <div className="flex items-center gap-1">
                              <span className="text-slate-400">Gap:</span>
                              <input
                                type="text"
                                value={step.keyDelay}
                                onChange={(e) => updateStep(step.id, { keyDelay: e.target.value })}
                                onBlur={() => updateStep(step.id, { keyDelay: formatDelay(step.keyDelay) })}
                                className="w-11 bg-[#0b0d12] border border-[#2c3244] rounded-md px-1.5 py-0.5 text-center font-mono text-[11px] text-slate-200 outline-none"
                              />
                              <span className="text-slate-400">s</span>
                            </div>
                          </div>
                        )}

                        {/* KEY STEP */}
                        {step.type === 'key' && (
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1 font-semibold text-white">
                              <Keyboard className="w-3.5 h-3.5 text-emerald-400" />
                              <span>{step.keyMode === 'release' ? 'Key Release' : step.keyMode === 'hold' ? 'Key Press' : 'Key'}</span>
                            </div>
                            <select
                              aria-label="Select key"
                              value={step.keyName}
                              disabled={step.keyMode === 'release'}
                              onChange={(e) => updateStep(step.id, { keyName: e.target.value })}
                              className="bg-[#0b0d12] border border-[#2c3244] rounded-lg px-2 py-1 text-[11px] text-slate-200 outline-none"
                            >
                              {KEY_OPTIONS.map((key) => <option key={key}>{key}</option>)}
                            </select>
                            {step.keyMode === 'release' ? (
                              <span className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-emerald-300">Release</span>
                            ) : (
                              <select
                                aria-label="Key action"
                                value={step.keyMode}
                                onChange={(e) => setKeyMode(step, e.target.value)}
                                className="bg-[#0b0d12] border border-[#2c3244] rounded-lg px-2 py-1 text-[11px] text-slate-200 outline-none"
                              >
                                <option value="press">Press</option>
                                <option value="hold">Hold</option>
                              </select>
                            )}
                            {step.keyMode !== 'release' && (
                              <div className="flex items-center gap-1" title="Hold these keys together with the key (shortcuts like Ctrl + C)">
                                {MODIFIER_KEYS.map((mod) => {
                                  const on = (step.modifiers || []).includes(mod);
                                  return (
                                    <button
                                      key={mod}
                                      type="button"
                                      aria-pressed={on}
                                      onClick={() => updateStep(step.id, {
                                        modifiers: on ? step.modifiers.filter((m) => m !== mod) : [...(step.modifiers || []), mod],
                                      })}
                                      className={`px-1.5 py-0.5 rounded-md border text-[10px] font-semibold ${
                                        on ? 'bg-emerald-500/15 border-emerald-400/50 text-emerald-200' : 'bg-[#0b0d12] border-[#2c3244] text-slate-500'
                                      }`}
                                    >
                                      {mod}
                                    </button>
                                  );
                                })}
                              </div>
                            )}
                            {step.keyMode === 'hold' && (
                              <span className="text-cyan-300">Press → Delay → Release</span>
                            )}
                          </div>
                        )}

                        {/* DRAG STEP */}
                        {step.type === 'drag' && (
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1 font-semibold text-white">
                              <Hand className="w-3.5 h-3.5 text-orange-400" />
                              <span>Drag</span>
                            </div>
                            {[['coords', step.id, 'from'], ['to', `${step.id}::to`, 'to']].map(([field, pickId, label]) => (
                              <button
                                key={field}
                                onClick={() => simulateCoordinatePick(pickId)}
                                title={`Pick where the drag ${label === 'from' ? 'starts' : 'ends'}`}
                                className="flex items-center gap-1 px-2 py-1 rounded-lg font-medium bg-[#14283c] hover:bg-[#1b3550] text-[#38bdf8] border border-[#23476b]"
                              >
                                <Crosshair className="w-3 h-3" />
                                <span>
                                  {pickingStepId === pickId ? 'Pick...' : `${label} ${step[field]?.x ?? 0},${step[field]?.y ?? 0}`}
                                </span>
                              </button>
                            ))}
                            <select
                              aria-label="Drag button"
                              value={step.button}
                              onChange={(e) => updateStep(step.id, { button: e.target.value })}
                              className="bg-[#0b0d12] border border-[#2c3244] rounded-lg px-2 py-1 text-[11px] text-slate-200 outline-none"
                            >
                              <option value="Left click">Left</option>
                              <option value="Right click">Right</option>
                              <option value="Middle click">Middle</option>
                            </select>
                            <label className="flex items-center gap-1 text-slate-400">
                              Time
                              <input
                                type="text"
                                inputMode="decimal"
                                aria-label="Drag duration in seconds"
                                value={step.duration}
                                onChange={(e) => updateStep(step.id, { duration: e.target.value.replace(/[^0-9,.]/g, '') })}
                                onBlur={() => updateStep(step.id, { duration: formatDelay(step.duration || '0,6') })}
                                className="w-11 bg-[#0b0d12] border border-[#2c3244] rounded-md px-1.5 py-1 text-center font-mono text-[11px] text-slate-200 outline-none"
                              />
                              <span>s</span>
                            </label>
                          </div>
                        )}

                        {/* SCROLL STEP */}
                        {step.type === 'scroll' && (
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1 font-semibold text-white">
                              <ArrowUpDown className="w-3.5 h-3.5 text-teal-400" />
                              <span>Scroll</span>
                            </div>
                            <button
                              onClick={() => simulateCoordinatePick(step.id)}
                              className="flex items-center gap-1 px-2 py-1 rounded-lg font-medium bg-[#14283c] hover:bg-[#1b3550] text-[#38bdf8] border border-[#23476b]"
                            >
                              <Crosshair className="w-3 h-3" />
                              <span>{pickingStepId === step.id ? 'Pick...' : `X:${step.coords.x} Y:${step.coords.y}`}</span>
                            </button>
                            <input
                              type="text"
                              inputMode="numeric"
                              aria-label="Scroll amount in notches"
                              value={step.amount}
                              onChange={(e) => updateStep(step.id, { amount: e.target.value.replace(/[^0-9-]/g, '').slice(0, 4) })}
                              onBlur={() => updateStep(step.id, { amount: String(Math.max(-100, Math.min(100, parseInt(step.amount, 10) || -3))) })}
                              className="w-12 bg-[#0b0d12] border border-[#2c3244] rounded-md px-1.5 py-1 text-center font-mono text-[11px] text-teal-200 outline-none"
                            />
                            <span className="text-slate-400">notches ({Number(step.amount) > 0 ? 'up' : 'down'}; minus = down)</span>
                          </div>
                        )}

                        {/* REPEAT BLOCK */}
                        {step.type === 'loop' && (
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1 font-semibold text-white">
                              <Repeat className="w-3.5 h-3.5 text-sky-400" />
                              <span>Repeat</span>
                            </div>
                            <input
                              type="text"
                              inputMode="numeric"
                              aria-label="Repeat count"
                              value={step.times}
                              onChange={(e) => updateStep(step.id, { times: e.target.value.replace(/[^0-9]/g, '') })}
                              onBlur={() => updateStep(step.id, { times: String(Math.min(1000, Math.max(1, parseInt(step.times, 10) || 1))) })}
                              className="w-12 bg-[#0b0d12] border border-[#2c3244] rounded-md px-1.5 py-1 text-center font-mono text-[11px] text-sky-200 outline-none"
                            />
                            <span className="text-slate-400">times: the steps up to "End repeat"</span>
                          </div>
                        )}
                        {step.type === 'loopEnd' && (
                          <div className="flex items-center gap-1 font-semibold text-sky-300 text-[11px]">
                            <Repeat className="w-3.5 h-3.5" />
                            <span>End repeat</span>
                          </div>
                        )}

                        {/* DELAY STEP */}
                        {step.type === 'delay' && (
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1 font-semibold text-white">
                              <Clock className="w-3.5 h-3.5 text-amber-400" />
                              <span>Delay</span>
                            </div>

                            <div className="flex items-center gap-1">
                              <span className="text-slate-400">Wait:</span>
                              <input
                                type="text"
                                value={step.duration}
                                onChange={(e) => updateStep(step.id, { duration: e.target.value })}
                                onBlur={() => updateStep(step.id, { duration: formatDelay(step.duration) })}
                                className="w-12 bg-[#0b0d12] border border-[#2c3244] rounded-md px-1.5 py-0.5 text-center font-mono text-[11px] text-amber-200 outline-none"
                              />
                              <span className="text-slate-400">sec</span>
                            </div>

                          </div>
                        )}
                      </div>

                      {/* Right Actions: run chance, Copy / Delete + Drag Handle */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {!['loop', 'loopEnd'].includes(step.type) && !step.holdOwnerId && (
                          <label
                            title="Chance to run this step each time it comes up (100% = always). Lower it to skip the step now and then."
                            className={`flex items-center gap-0.5 px-1.5 py-1 rounded-md border text-[10px] font-mono ${
                              Number(step.chance ?? 100) < 100
                                ? 'bg-violet-500/10 border-violet-400/40 text-violet-200'
                                : 'bg-[#0b0d12] border-[#2c3244] text-slate-400'
                            }`}
                          >
                            <input
                              type="text"
                              inputMode="numeric"
                              aria-label="Run chance in percent"
                              value={step.chance ?? '100'}
                              onChange={(e) => updateStep(step.id, { chance: e.target.value.replace(/[^0-9]/g, '').slice(0, 3) })}
                              onBlur={() => updateStep(step.id, { chance: String(Math.min(100, Math.max(0, parseInt(step.chance, 10) || 0))) })}
                              className="w-6 bg-transparent text-right outline-none"
                            />
                            <span>%</span>
                          </label>
                        )}
                        <div className="flex flex-col gap-1">
                          <button
                            onClick={() => duplicateStep(step)}
                            disabled={step.type === 'loop' || step.type === 'loopEnd'}
                            className="px-2 py-0.5 rounded bg-[#1f2433] hover:bg-[#2a3145] border border-[#2f374d] text-[10px] font-medium text-slate-200 disabled:opacity-30 disabled:pointer-events-none"
                          >
                            Copy
                          </button>
                          <button
                            onClick={() => deleteStep(step.id)}
                            className="px-2 py-0.5 rounded bg-[#26181c] hover:bg-[#3a1f26] border border-red-500/25 text-[10px] font-medium text-red-400"
                          >
                            Delete
                          </button>
                        </div>

                        <div
                          data-drag-handle
                          onPointerDown={(event) => {
                            if (event.button !== 0) return;
                            event.preventDefault();
                            const card = event.currentTarget.closest('[data-step-id]');
                            const preview = card.cloneNode(true);
                            const rect = card.getBoundingClientRect();
                            dragOffsetRef.current = { x: event.clientX - rect.left, y: event.clientY - rect.top };
                            preview.removeAttribute('data-step-id');
                            preview.setAttribute('aria-hidden', 'true');
                            Object.assign(preview.style, {
                              position: 'fixed', left: `${rect.left}px`, top: `${rect.top}px`,
                              width: `${rect.width}px`, margin: '0', opacity: '0.96', zIndex: '9999',
                              pointerEvents: 'none', transform: 'none', transition: 'none',
                              boxShadow: '0 16px 40px rgba(0,0,0,.55)',
                            });
                            document.body.appendChild(preview);
                            dragPreviewRef.current = preview;
                            dropTargetRef.current = null;
                            setDraggedStepId(step.id);
                          }}
                          className="p-1 rounded bg-[#0e1118] border border-[#222736] text-slate-500 cursor-grab active:cursor-grabbing touch-none"
                        >
                          <GripVertical className="w-3.5 h-3.5" />
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* ================= RIGHT SIDEBAR MENU (3 COLS) ================= */}
          <div className="lg:col-span-3 flex flex-col gap-3 min-h-0 overflow-y-auto pl-0.5">
            
            {/* RIGHT CARD 1: Global Random Delay */}
            <div className="rounded-xl bg-[#13161f] border border-[#1e2332] p-3.5 space-y-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className={`transition-opacity ${globalDelayEnabled ? 'opacity-100' : 'opacity-45'}`}>
                  <div className="flex items-center gap-1.5">
                    <Timer className="w-3.5 h-3.5 text-[#38bdf8]" />
                    <h3 className="text-xs font-bold text-[#38bdf8]">Global Random Delay</h3>
                  </div>
                  <p className="text-[10px] text-slate-400">Delay added between actions</p>
                </div>
                <label className="flex items-center gap-1.5 text-[10px] text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={globalDelayEnabled}
                    onChange={(e) => setGlobalDelayEnabled(e.target.checked)}
                    className="accent-[#0A84FF]"
                  />
                  Enabled
                </label>
              </div>

              <div className={`space-y-2.5 transition-opacity ${globalDelayEnabled ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
                {isMinGreaterThanMax && (
                  <button
                    onClick={swapMinMax}
                    className="flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/30 text-[10px] font-medium text-amber-300 hover:bg-amber-500/25"
                  >
                    <AlertTriangle className="w-3 h-3" />
                    <span>Fix min/max</span>
                  </button>
                )}
                <div className="grid grid-cols-2 gap-2">
                <div className="bg-[#0b0d12] border border-[#252a3a] rounded-lg p-2 flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">Min</span>
                  <div className="flex items-center gap-1">
                    <input
                      type="text"
                      value={minDelay}
                      onChange={(e) => {
                        const value = e.target.value;
                        setMinDelay(value);
                        const numericValue = parseFloat(value.replace(',', '.'));
                        if (Number.isFinite(numericValue)) {
                          setMaxDelay(formatDelay(numericValue * 1.4));
                        }
                      }}
                      onBlur={() => {
                        const normalizedMin = formatDelay(minDelay);
                        setMinDelay(normalizedMin);
                        const numericValue = parseFloat(String(normalizedMin).replace(',', '.'));
                        if (Number.isFinite(numericValue)) setMaxDelay(formatDelay(numericValue * 1.4));
                      }}
                      className="w-10 bg-transparent text-right font-mono text-xs font-semibold text-white outline-none"
                    />
                    <span className="text-[10px] text-slate-500">s</span>
                  </div>
                </div>

                <div className="bg-[#0b0d12] border border-[#252a3a] rounded-lg p-2 flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">Max</span>
                  <div className="flex items-center gap-1">
                    <input
                      type="text"
                      value={maxDelay}
                      onChange={(e) => setMaxDelay(e.target.value)}
                      onBlur={() => setMaxDelay(formatDelay(maxDelay))}
                      className="w-10 bg-transparent text-right font-mono text-xs font-semibold text-white outline-none"
                    />
                    <span className="text-[10px] text-slate-500">s</span>
                  </div>
                </div>
                </div>
              </div>
            </div>

            {/* RIGHT CARD 2: Movement Settings + Bezier & Jitter Visualizer */}
            <div className="rounded-xl bg-[#13161f] border border-[#1e2332] p-3.5 space-y-2.5">
              <div className="flex items-center justify-between">
                <div className={`flex items-center gap-1.5 transition-opacity ${movementEnabled ? 'opacity-100' : 'opacity-45'}`}>
                  <BrainCircuit className="w-3.5 h-3.5 text-pink-400" />
                  <h3 className="text-xs font-bold text-[#38bdf8]">Movement Settings</h3>
                </div>
                <label className="flex items-center gap-1.5 text-[10px] text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={movementEnabled}
                    onChange={(e) => setMovementEnabled(e.target.checked)}
                    className="accent-[#0A84FF]"
                  />
                  Enabled
                </label>
              </div>

              <div className={`space-y-2.5 transition-opacity ${movementEnabled ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
              {/* Live SVG Bezier Curve & Target Jitter Visualizer */}
              <div className="h-16 w-full rounded-lg bg-[#090b10] border border-[#1d2230] px-2.5 flex items-center justify-between relative overflow-hidden">
                <svg className="w-full h-full overflow-visible" viewBox="0 0 240 54">
                  <defs>
                    <linearGradient id="curveGrad16x9" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#0A84FF" />
                      <stop offset="100%" stopColor="#00D2FF" />
                    </linearGradient>
                  </defs>
                  <line
                    x1="16"
                    y1="40"
                    x2="220"
                    y2="16"
                    stroke="#1e2433"
                    strokeWidth="1"
                    strokeDasharray="3 3"
                  />
                  <path
                    d={irregularPath}
                    fill="none"
                    stroke="url(#curveGrad16x9)"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                  />
                  <circle cx="16" cy="40" r="3" fill="#0A84FF" />
                  {/* Target Jitter Radius Visualization */}
                  <circle
                    cx="220"
                    cy="16"
                    r={Math.min(Math.max(numericJitter * 1.8, 4), 16)}
                    fill="rgba(0, 210, 255, 0.12)"
                    stroke="#00D2FF"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                  />
                  <circle cx="220" cy="16" r="3" fill="#00D2FF" />
                </svg>
                <span className="absolute bottom-1 right-2 text-[9px] font-mono text-slate-500">
                  Irregularity {curvePercent}% · Jitter {targetJitter}px
                </span>
              </div>

              <div className="space-y-2 text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="text-slate-300">Mouse speed:</span>
                  <div className="flex items-center bg-[#0b0d12] border border-[#282e40] rounded-lg px-2 py-1">
                    <input
                      type="text"
                      value={mouseSpeed}
                      onChange={(e) => setMouseSpeed(e.target.value)}
                      className="w-9 bg-transparent text-right font-mono text-xs text-white outline-none"
                    />
                    <span className="text-slate-400 ml-1 font-mono">x</span>
                  </div>
                </div>

                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-300" title="How irregular the mouse path is: 0 = straight line, higher = S-shaped, wobbly, human-like">Irregularity:</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={curvePercent}
                    onChange={(e) => setCurvePercent(Number(e.target.value))}
                    className="flex-1 accent-[#0A84FF] h-1 bg-[#0b0d12] rounded-lg cursor-pointer"
                  />
                  <div className="flex items-center bg-[#0b0d12] border border-[#282e40] rounded-lg px-2 py-1">
                    <input
                      type="number"
                      value={curvePercent}
                      onChange={(e) => setCurvePercent(Number(e.target.value))}
                      className="w-7 bg-transparent text-right font-mono text-xs text-white outline-none"
                    />
                    <span className="text-slate-400 ml-0.5 font-mono">%</span>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-300">Target jitter:</span>
                  <div className="flex items-center bg-[#0b0d12] border border-[#282e40] rounded-lg px-2 py-1">
                    <input
                      type="text"
                      value={targetJitter}
                      onChange={(e) => setTargetJitter(e.target.value)}
                      className="w-9 bg-transparent text-right font-mono text-xs text-white outline-none"
                    />
                    <span className="text-slate-400 ml-1 font-mono">px</span>
                  </div>
                </div>
              </div>
              </div>
            </div>

            {/* RIGHT CARD: Background Mode - input goes to one window, real mouse/keyboard stay free */}
            <div className="rounded-xl bg-[#13161f] border border-[#1e2332] p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <div className={`flex items-center gap-1.5 transition-opacity ${backgroundEnabled ? 'opacity-100' : 'opacity-45'}`}>
                  <AppWindow className="w-3.5 h-3.5 text-emerald-400" />
                  <h3 className="text-xs font-bold text-[#38bdf8]">Background Mode</h3>
                </div>
                <label className="flex items-center gap-1.5 text-[10px] text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={backgroundEnabled}
                    disabled={!target}
                    onChange={(e) => setBackgroundEnabled(e.target.checked)}
                    className="accent-[#0A84FF]"
                  />
                  Enabled
                </label>
              </div>
              <p className="text-[10px] text-slate-500 leading-snug">
                Your mouse and keyboard stay free: clicks and keys go to the picked window. It can stay behind other windows, but not minimized.
              </p>
              <div className="relative">
                <button
                  onClick={async () => {
                    if (!nativeReady) return showToast('Window picking works in the desktop app');
                    if (targetMenu) return setTargetMenu(null);
                    setTargetMenu(await window.notafkBridge.listWindows());
                  }}
                  className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] hover:bg-[#0f1219] border border-[#252b3d] text-xs text-left flex items-center justify-between gap-2 transition-colors"
                >
                  <span className={`truncate font-medium ${target ? 'text-slate-200' : 'text-slate-500'}`}>
                    {target ? target.title : 'Choose target window'}
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                </button>
                {targetMenu && (
                  <div className="absolute left-0 right-0 top-full mt-1 max-h-56 overflow-y-auto rounded-xl bg-[#161a25] border border-[#2c3246] shadow-2xl py-1 z-40">
                    {targetMenu.length === 0 && (
                      <div className="px-3 py-1.5 text-[11px] text-slate-500">No open windows found</div>
                    )}
                    {targetMenu.map((win) => (
                      <button
                        key={win.hwnd}
                        onClick={() => {
                          setTargetMenu(null);
                          setTarget(win);
                          setBackgroundEnabled(true);
                          pushLog(`Background target: "${win.title}"`, 'ready');
                        }}
                        className={`w-full px-3 py-1.5 text-xs text-left hover:bg-blue-500/15 block truncate ${
                          target?.hwnd === win.hwnd ? 'text-blue-200' : 'text-slate-300'
                        }`}
                      >
                        {win.title}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* RIGHT CARD 3: Live Execution Telemetry Log */}
            <div className="rounded-xl bg-[#13161f] border border-[#1e2332] p-3 flex-1 min-h-[120px] flex flex-col">
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-[#38bdf8]" />
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-300">
                    Live Telemetry
                  </span>
                </div>
                <span className="text-[10px] font-mono text-slate-500">Real-time</span>
              </div>

              <div className="flex-1 bg-[#090b10] border border-[#1b202e] rounded-lg p-2 overflow-y-auto space-y-1 font-mono text-[10px]">
                {logs.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-1.5 leading-tight">
                    <span className="text-slate-600 shrink-0">{item.time}</span>
                    <span
                      className={
                        item.type === 'exec'
                          ? 'text-blue-400'
                          : item.type === 'ready'
                          ? 'text-emerald-400'
                          : item.type === 'warn'
                          ? 'text-amber-400'
                          : 'text-slate-300'
                      }
                    >
                      {item.msg}
                    </span>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
