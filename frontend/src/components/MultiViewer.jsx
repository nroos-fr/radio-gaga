import React, { useRef, useEffect, useState, useCallback, useImperativeHandle, forwardRef } from 'react';
import * as cornerstone from '@cornerstonejs/core';
import * as cornerstoneTools from '@cornerstonejs/tools';
import { initCornerstoneServices } from '../cornerstoneInit';
import {
  FiSun, FiMove, FiZoomIn,
  FiChevronLeft, FiChevronRight,
  // FiEye, FiEyeOff, // ← uncomment when re-enabling the seg toggle button
} from 'react-icons/fi';
import '../styles/MultiViewer.css';

const {
  WindowLevelTool,
  StackScrollTool,
  ZoomTool,
  PanTool,
  ReferenceLinesTool,
} = cornerstoneTools;

const RENDERING_ENGINE_ID = 'RG_MPR_ENGINE';
const TOOL_GROUP_ID       = 'RG_MPR_TOOLS';

// Viewport descriptors — order matters (torax is the default reference source)
const VIEWPORTS = [
  { id: 'VP_TORAX',   key: 'torax',   label: 'CT Thorax',   accent: '#4fc3f7' },
  { id: 'VP_ABDOMEN', key: 'abdomen', label: 'CT Abdomen',  accent: '#81c784' },
  { id: 'VP_COLUMNA', key: 'columna', label: 'CT Columna ↕', accent: '#ffb74d' },
];

const INTERACT_TOOLS = [
  { name: WindowLevelTool.toolName, label: 'W/L',  icon: FiSun },
  { name: PanTool.toolName,         label: 'Pan',  icon: FiMove },
  { name: ZoomTool.toolName,        label: 'Zoom', icon: FiZoomIn },
];

const MultiViewer = forwardRef(function MultiViewer({
  studyId,
  onMetadataUpdate,
  onSeriesLoad,
  onSliceChange,
  lesions = [],
  showPngMask = false,
  onTogglePngMask,
  onJumpToLesion,
}, ref) {
  // One DOM ref per viewport key
  const divRefs   = useRef({ torax: null, abdomen: null, columna: null });
  const engineRef = useRef(null);
  const tgRef     = useRef(null);
  const imageIds  = useRef({ torax: [], abdomen: [], columna: [] });

  const [status, setStatus]     = useState('loading'); // 'loading' | 'ready' | 'error'
  const [errorMsg, setErrorMsg] = useState('');
  const [slices, setSlices]     = useState({
    torax:   { cur: 0, total: 0 },
    abdomen: { cur: 0, total: 0 },
    columna: { cur: 0, total: 0 },
  });
  const [activeTool, setActiveTool] = useState(WindowLevelTool.toolName);  const [showSeg, setShowSeg]       = useState(false);
  const [segData, setSegData]       = useState(null);
  const [segLoading, setSegLoading] = useState(false);
  const overlayRefs = useRef({ torax: null, abdomen: null, columna: null });
  const showSegRef  = useRef(false);
  const segDataRef  = useRef(null);

  // Keep refs in sync with state so event-listener callbacks always read fresh values
  useEffect(() => { showSegRef.current = showSeg; }, [showSeg]);
  useEffect(() => { segDataRef.current = segData;  }, [segData]);
  // ─── Setup ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    const setup = async () => {
      await initCornerstoneServices();
      if (cancelled) return;

      // 1. Rendering engine
      const engine = new cornerstone.RenderingEngine(RENDERING_ENGINE_ID);
      engineRef.current = engine;

      // 2. Enable one stack viewport per panel
      VIEWPORTS.forEach(({ id, key }) => {
        engine.enableElement({
          viewportId: id,
          type: cornerstone.Enums.ViewportType.STACK,
          element: divRefs.current[key],
          defaultOptions: { background: [0.02, 0.02, 0.02] },
        });
      });

      // 3. Tool group
      let tg = cornerstoneTools.ToolGroupManager.getToolGroup(TOOL_GROUP_ID);
      if (!tg) tg = cornerstoneTools.ToolGroupManager.createToolGroup(TOOL_GROUP_ID);
      tgRef.current = tg;

      // Register tools globally (safe to call multiple times)
      [WindowLevelTool, StackScrollTool, ZoomTool, PanTool,
       ReferenceLinesTool].forEach((T) => {
        try { cornerstoneTools.addTool(T); } catch (_) {}
      });

      // Bind all three viewports to this tool group
      VIEWPORTS.forEach(({ id }) => tg.addViewport(id, RENDERING_ENGINE_ID));

      // Add tools to the group
      [WindowLevelTool, StackScrollTool, ZoomTool, PanTool,
       ReferenceLinesTool].forEach(({ toolName }) => {
        try { tg.addTool(toolName); } catch (_) {}
      });

      // Default mouse bindings
      tg.setToolActive(WindowLevelTool.toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Primary }],
      });
      tg.setToolActive(PanTool.toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Auxiliary }],
      });
      tg.setToolActive(ZoomTool.toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Secondary }],
      });
      // In Cornerstone v4, mouse wheel scroll is a binding on StackScrollTool
      tg.setToolActive(StackScrollTool.toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Wheel }],
      });

      // Reference lines — display tool, no left-click binding needed
      tg.setToolEnabled(ReferenceLinesTool.toolName);

      // 4. Fetch series URLs from backend
      const encodedId = studyId.split('/').map(encodeURIComponent).join('/');
      const res = await fetch(`/api/series/${encodedId}`);
      if (!res.ok) throw new Error(`Backend returned ${res.status}. Is it running on :8000?`);
      const series = await res.json();

      // 5. Load each series into its viewport, starting at the middle slice
      for (const { id, key } of VIEWPORTS) {
        const urls = series[key] ?? [];
        if (!urls.length) continue;

        const ids = urls.map((u) => `wadouri:${u}`);
        imageIds.current[key] = ids;

        const mid = Math.floor(ids.length / 2);
        const vp  = engine.getViewport(id);
        await vp.setStack(ids, mid);
        vp.render();

        setSlices((prev) => ({
          ...prev,
          [key]: { cur: mid + 1, total: ids.length },
        }));
      }

      // 6. Notify parent with torax series info
      const toraxUrls = series.torax ?? [];
      onSeriesLoad?.(toraxUrls.map((u) => u.split('/').pop()));

      // 7. Initial metadata from torax midpoint
      const toraxIds = imageIds.current.torax;
      if (toraxIds.length) {
        const mid = Math.floor(toraxIds.length / 2);
        cornerstone.imageLoader
          .loadImage(toraxIds[mid])
          .then((img) => onMetadataUpdate?.(img.data, mid))
          .catch(() => {});
      }

      // 8. Per-viewport event listeners
      for (const { id, key } of VIEWPORTS) {
        const el = divRefs.current[key];

        // Update slice counter and metadata on scroll
        el.addEventListener(cornerstone.EVENTS.STACK_NEW_IMAGE, (evt) => {
          const { imageIndex } = evt.detail;
          setSlices((prev) => ({ ...prev, [key]: { ...prev[key], cur: imageIndex + 1 } }));
          if (key === 'torax') {
            onSliceChange?.(imageIndex);
            cornerstone.imageLoader
              .loadImage(imageIds.current.torax[imageIndex])
              .then((img) => onMetadataUpdate?.(img.data, imageIndex))
              .catch(() => {});
          }
        });

        // Make the interacted viewport the reference-line source so lines
        // are always drawn relative to whichever panel the user is scrolling
        const makeSource = () => {
          tgRef.current?.setToolConfiguration(ReferenceLinesTool.toolName, {
            sourceViewportId: id,
            showFullDimension: true,
          });
        };
        el.addEventListener('pointerdown', makeSource);
        el.addEventListener('wheel', makeSource, { passive: true });
        // Redraw seg contours after every Cornerstone render (handles pan/zoom)
        el.addEventListener(cornerstone.EVENTS.IMAGE_RENDERED, () => drawContoursForKey(key));
      }

      // 9. Initialise reference lines with torax as default source
      tg.setToolConfiguration(ReferenceLinesTool.toolName, {
        sourceViewportId: VIEWPORTS[0].id,
        showFullDimension: true,
      });

      if (!cancelled) setStatus('ready');
    };

    setup().catch((err) => {
      console.error('[MultiViewer] setup error:', err);
      if (!cancelled) { setStatus('error'); setErrorMsg(err.message); }
    });

    return () => {
      cancelled = true;
      try {
        cornerstoneTools.ToolGroupManager.destroyToolGroup(TOOL_GROUP_ID);
        engineRef.current?.destroy();
      } catch (_) {}
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // ─── Seg contour drawing ──────────────────────────────────────────────────────
  // Reads from refs — stable function, safe to call from event listeners
  const drawContoursForKey = useCallback((key) => {
    const canvas = overlayRefs.current[key];
    if (!canvas) return;
    const vpDesc  = VIEWPORTS.find((v) => v.key === key);
    const viewport = engineRef.current?.getViewport(vpDesc?.id);
    if (!viewport) return;

    const container = divRefs.current[key];
    canvas.width  = container?.clientWidth  ?? 0;
    canvas.height = container?.clientHeight ?? 0;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!showSegRef.current || !segDataRef.current) return;

    const seriesContours = segDataRef.current[key];
    if (!seriesContours) return;

    let sliceIdx;
    try { sliceIdx = viewport.getCurrentImageIdIndex(); } catch { return; }

    const contourList = seriesContours[String(sliceIdx)];
    if (!contourList?.length) return;

    let vtkImgData;
    try { vtkImgData = viewport.getImageData()?.imageData; } catch { return; }
    if (!vtkImgData) return;

    ctx.strokeStyle = '#ff3333';
    ctx.lineWidth   = 1.5;
    ctx.lineJoin    = 'round';
    ctx.shadowColor = 'rgba(255,0,0,0.55)';
    ctx.shadowBlur  = 5;

    for (const contour of contourList) {
      if (contour.length < 2) continue;
      ctx.beginPath();
      contour.forEach(([col, row], i) => {
        try {
          const world = vtkImgData.indexToWorldVec3([col, row, 0]);
          const [cx, cy] = viewport.worldToCanvas(world);
          if (i === 0) ctx.moveTo(cx, cy); else ctx.lineTo(cx, cy);
        } catch { /* skip bad point */ }
      });
      ctx.closePath();
      ctx.stroke();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-render all viewports when showSeg / segData changes → triggers IMAGE_RENDERED → drawContours
  useEffect(() => {
    VIEWPORTS.forEach(({ id }) => {
      try { engineRef.current?.getViewport(id)?.render(); } catch (_) {}
    });
  }, [showSeg, segData]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Fetch / toggle segmentation ────────────────────────────────────────────────────
  const fetchSeg = useCallback(async () => {
    if (segData) {
      // Already loaded — just toggle visibility
      const next = !showSeg;
      showSegRef.current = next;
      setShowSeg(next);
      return;
    }
    // First load
    setSegLoading(true);
    try {
      const encodedId = studyId.split('/').map(encodeURIComponent).join('/');
      const res  = await fetch(`/api/seg/${encodedId}`);
      const data = await res.json();
      segDataRef.current = data;
      showSegRef.current = true;
      setSegData(data);
      setShowSeg(true);
    } catch (e) {
      console.error('[MultiViewer] failed to load segmentation', e);
    } finally {
      setSegLoading(false);
    }
  }, [showSeg, segData, studyId]); // eslint-disable-line react-hooks/exhaustive-deps
  // ─── Navigation ─────────────────────────────────────────────────────────────
  const goToSlice = useCallback((key, index) => {
    const ids = imageIds.current[key];
    if (!ids.length) return;
    const vpId = VIEWPORTS.find((v) => v.key === key)?.id;
    if (!vpId) return;
    const clamped = Math.max(0, Math.min(index, ids.length - 1));
    const vp = engineRef.current?.getViewport(vpId);
    if (!vp) return;
    vp.setImageIdIndex(clamped)
      .then(() => {
        vp.render();
        // Update counter directly — don't rely solely on the event
        setSlices((prev) => ({ ...prev, [key]: { ...prev[key], cur: clamped + 1 } }));
        if (key === 'torax') {
          onSliceChange?.(clamped);
          cornerstone.imageLoader
            .loadImage(ids[clamped])
            .then((img) => onMetadataUpdate?.(img.data, clamped))
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, [onMetadataUpdate]);

  // ─── Imperative handle — lets parent call goToSlice directly ────────────────
  useImperativeHandle(ref, () => ({
    goToSlice,
  }), [goToSlice]);

  // ─── Left-click tool switch ──────────────────────────────────────────────────
  const switchTool = useCallback((name) => {
    const tg = tgRef.current;
    if (!tg) return;
    INTERACT_TOOLS.forEach(({ name: n }) => tg.setToolPassive(n));
    tg.setToolActive(name, {
      bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Primary }],
    });
    setActiveTool(name);
  }, []);

  // ─── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="multi-viewer">
      {/* ── Toolbar ── */}
      <div className="mv-toolbar">
        <span className="mv-title">MPR Viewer — {studyId.split('/').pop()}</span>
        <div className="mv-tools">
          {INTERACT_TOOLS.map(({ name, label, icon: Icon }) => (
            <button
              key={name}
              className={`mv-tool-btn${activeTool === name ? ' mv-tool-active' : ''}`}
              onClick={() => switchTool(name)}
              title={label}
            >
              <Icon size={13} />
              <span>{label}</span>
            </button>
          ))}
        </div>
        {/* ── Seg toggle button — uncomment to re-enable ──────────────────────
        <button
          className={`mv-tool-btn mv-seg-btn${showSeg ? ' mv-seg-active' : ''}`}
          onClick={fetchSeg}
          disabled={segLoading}
          title="Toggle segmentation overlay"
        >
          {segLoading
            ? <span className="mv-seg-spinner" />
            : showSeg ? <FiEyeOff size={13} /> : <FiEye size={13} />}
          <span>{segLoading ? 'Loading…' : showSeg ? 'Hide seg' : 'Show seg'}</span>
        </button>
        ─────────────────────────────────────────────────────────────────────── */}

        {/* ── PNG mask toggle + lesion jump buttons (visible after analysis) ── */}
        {lesions.length > 0 && (
          <>
            <button
              className={`mv-tool-btn mv-mask-btn${showPngMask ? ' mv-mask-active' : ''}`}
              onClick={onTogglePngMask}
              title="Show/hide mask in PNG scroller (left panel)"
            >
              <span style={{ fontSize: 11 }}>🎭</span>
              <span>{showPngMask ? 'Hide mask' : 'Show mask'}</span>
            </button>
            {lesions.map(l => (
              <button
                key={l.lesion_id}
                className="mv-tool-btn mv-lesion-btn"
                onClick={() => onJumpToLesion?.(l.slice_index)}
                title={`Jump to lesion ${l.lesion_id} — center slice ${l.slice_index} (±${l.slice_min}–${l.slice_max})`}
              >
                L{l.lesion_id}
              </button>
            ))}
          </>
        )}
        <span className="mv-hint">Scroll any panel — reference line updates on others</span>
      </div>

      {/* ── Viewport grid ── */}
      <div className="mv-grid">
        {VIEWPORTS.map(({ key, label, accent }) => {
          const { cur, total } = slices[key];
          return (
            <div key={key} className="mv-pane">

              {/* Pane header */}
              <div className="mv-pane-header" style={{ borderBottomColor: accent }}>
                <span className="mv-pane-title" style={{ color: accent }}>{label}</span>
                {total > 0 && (
                  <span className="mv-pane-count">{cur} / {total}</span>
                )}
              </div>

              {/* Cornerstone canvas + seg overlay */}
              <div className="mv-pane-body">
                <div
                  ref={(el) => { if (el) divRefs.current[key] = el; }}
                  className="mv-cs-viewport"
                />
                <canvas
                  ref={(el) => { if (el) overlayRefs.current[key] = el; }}
                  className="mv-seg-overlay"
                />
                {status === 'loading' && (
                  <div className="mv-overlay-loading">
                    <div className="mv-spinner" />
                  </div>
                )}
              </div>

              {/* Slice navigation */}
              {total > 0 && (
                <div className="mv-nav">
                  <button
                    className="mv-nav-btn"
                    onClick={() => goToSlice(key, cur - 2)}
                    disabled={cur <= 1}
                  >
                    <FiChevronLeft size={14} />
                  </button>
                  <input
                    type="range"
                    className="mv-slider"
                    min={1}
                    max={total}
                    value={cur}
                    onChange={(e) => goToSlice(key, Number(e.target.value) - 1)}
                  />
                  <button
                    className="mv-nav-btn"
                    onClick={() => goToSlice(key, cur)}
                    disabled={cur >= total}
                  >
                    <FiChevronRight size={14} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Error banner ── */}
      {status === 'error' && (
        <div className="mv-error">
          ⚠️ Could not load DICOM series: {errorMsg}
        </div>
      )}
    </div>
  );
});

export default MultiViewer;
