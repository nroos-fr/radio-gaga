import React, { useRef, useEffect, useState, useCallback } from 'react';
import * as cornerstone from '@cornerstonejs/core';
import * as cornerstoneTools from '@cornerstonejs/tools';
import { initCornerstoneServices, cornerstoneDICOMImageLoader } from '../cornerstoneInit';
import {
  FiUploadCloud,
  FiChevronLeft,
  FiChevronRight,
  FiMaximize2,
  FiSun,
  FiMove,
  FiZoomIn,
} from 'react-icons/fi';
import '../styles/DicomViewer.css';

const VIEWPORT_ID = 'DICOM_STACK_VIEWPORT';
const RENDERING_ENGINE_ID = 'RADIO_GAGA_ENGINE';
const TOOL_GROUP_ID = 'RADIO_GAGA_TOOLS';

const {
  WindowLevelTool,
  StackScrollTool,
  ZoomTool,
  PanTool,
} = cornerstoneTools;

const TOOLS = [
  { name: WindowLevelTool.toolName, label: 'W/L', icon: FiSun },
  { name: PanTool.toolName, label: 'Pan', icon: FiMove },
  { name: ZoomTool.toolName, label: 'Zoom', icon: FiZoomIn },
];

export default function DicomViewer({
  onMetadataUpdate,
  onSeriesLoad,
  currentIndex,
  total,
}) {
  const divRef = useRef(null);
  const renderingEngineRef = useRef(null);
  const toolGroupRef = useRef(null);
  const imageIdsRef = useRef([]);
  const sliceListenerRef = useRef(null);

  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [hasImages, setHasImages] = useState(false);
  const [activeTool, setActiveTool] = useState(WindowLevelTool.toolName);
  const [localIndex, setLocalIndex] = useState(0);

  // ─── Init Cornerstone once on mount ───────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    const setup = async () => {
      await initCornerstoneServices();
      if (cancelled || !divRef.current) return;

      // Create rendering engine
      const engine = new cornerstone.RenderingEngine(RENDERING_ENGINE_ID);
      renderingEngineRef.current = engine;

      // Enable viewport element
      engine.enableElement({
        viewportId: VIEWPORT_ID,
        type: cornerstone.Enums.ViewportType.STACK,
        element: divRef.current,
        defaultOptions: { background: [0.02, 0.02, 0.02] },
      });

      // Tool group — reuse if already present (React StrictMode double-mount)
      let toolGroup = cornerstoneTools.ToolGroupManager.getToolGroup(TOOL_GROUP_ID);
      if (!toolGroup) {
        toolGroup = cornerstoneTools.ToolGroupManager.createToolGroup(TOOL_GROUP_ID);
      }
      toolGroupRef.current = toolGroup;

      [WindowLevelTool, StackScrollTool, ZoomTool, PanTool].forEach(
        (Tool) => { try { cornerstoneTools.addTool(Tool); } catch (_) {} }
      );

      toolGroup.addViewport(VIEWPORT_ID, RENDERING_ENGINE_ID);
      try { toolGroup.addTool(WindowLevelTool.toolName); } catch (_) {}
      try { toolGroup.addTool(StackScrollTool.toolName); } catch (_) {}
      try { toolGroup.addTool(ZoomTool.toolName); } catch (_) {}
      try { toolGroup.addTool(PanTool.toolName); } catch (_) {}

      // Default active tools
      toolGroup.setToolActive(WindowLevelTool.toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Primary }],
      });
      toolGroup.setToolActive(PanTool.toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Auxiliary }],
      });
      toolGroup.setToolActive(ZoomTool.toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Secondary }],
      });
      toolGroup.setToolActive(StackScrollTool.toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Wheel }],
      });

      setReady(true);
    };

    setup().catch(console.error);

    return () => {
      cancelled = true;
      try {
        cornerstoneTools.ToolGroupManager.destroyToolGroup(TOOL_GROUP_ID);
        renderingEngineRef.current?.destroy();
      } catch (_) {}
    };
  }, []);

  // ─── Sync slice index from parent ─────────────────────────────────────────
  useEffect(() => {
    setLocalIndex(currentIndex > 0 ? currentIndex - 1 : 0);
  }, [currentIndex]);

  // ─── Handle folder / file selection ───────────────────────────────────────
  const handleFileChange = useCallback(
    async (e) => {
      const allFiles = Array.from(e.target.files);
      const dcmFiles = allFiles
        .filter((f) => f.name.toLowerCase().endsWith('.dcm') || !f.name.includes('.'))
        .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));

      if (!dcmFiles.length) {
        alert('No DICOM (.dcm) files found in the selected folder.');
        return;
      }

      setLoading(true);
      onSeriesLoad?.(dcmFiles);

      try {
        // ✅ Use fileManager.add() — returns proper "dicomfile:N" imageIds
        //    (not blob URLs, which the dicomfile: scheme cannot handle)
        const imageIds = dcmFiles.map((file) =>
          cornerstoneDICOMImageLoader.wadouri.fileManager.add(file)
        );
        imageIdsRef.current = imageIds;

        const viewport = renderingEngineRef.current?.getViewport(VIEWPORT_ID);
        if (!viewport) throw new Error('Viewport not ready');

        await viewport.setStack(imageIds, 0);
        viewport.render();

        setHasImages(true);
        setLocalIndex(0);

        // Expose metadata of first image
        try {
          const image = await cornerstone.imageLoader.loadImage(imageIds[0]);
          onMetadataUpdate?.(image.data, 0);
        } catch (_) {}

        // Remove any previous slice-change listener before adding a new one
        if (sliceListenerRef.current && divRef.current) {
          divRef.current.removeEventListener(
            cornerstone.EVENTS.STACK_NEW_IMAGE,
            sliceListenerRef.current
          );
        }

        const onNewImage = (evt) => {
          const { imageIndex } = evt.detail;
          setLocalIndex(imageIndex);
          cornerstone.imageLoader
            .loadImage(imageIds[imageIndex])
            .then((img) => onMetadataUpdate?.(img.data, imageIndex))
            .catch(() => {});
        };
        sliceListenerRef.current = onNewImage;
        divRef.current?.addEventListener(cornerstone.EVENTS.STACK_NEW_IMAGE, onNewImage);
      } catch (err) {
        console.error('DICOM load error:', err);
      } finally {
        setLoading(false);
      }
    },
    [onMetadataUpdate, onSeriesLoad]
  );

  // ─── Navigate slices programmatically ─────────────────────────────────────
  const goToSlice = useCallback(
    async (index) => {
      const ids = imageIdsRef.current;
      if (!ids.length) return;
      const clamped = Math.max(0, Math.min(index, ids.length - 1));
      const viewport = renderingEngineRef.current?.getViewport(VIEWPORT_ID);
      if (!viewport) return;
      await viewport.setImageIdIndex(clamped);
      viewport.render();
    },
    []
  );

  // ─── Switch active left-click tool ────────────────────────────────────────
  const switchTool = useCallback(
    (toolName) => {
      const group = toolGroupRef.current;
      if (!group) return;
      TOOLS.forEach(({ name }) => {
        group.setToolPassive(name);
      });
      group.setToolActive(toolName, {
        bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Primary }],
      });
      setActiveTool(toolName);
    },
    []
  );

  const displayIndex = localIndex + 1;
  const displayTotal = imageIdsRef.current.length || total;

  return (
    <div className="dicom-viewer">
      {/* ── Top bar ── */}
      <div className="viewer-toolbar">
        <span className="viewer-toolbar-title">DICOM Viewer</span>
        <div className="viewer-tools">
          {TOOLS.map(({ name, label, icon: Icon }) => (
            <button
              key={name}
              className={`tool-btn ${activeTool === name ? 'tool-btn-active' : ''}`}
              onClick={() => switchTool(name)}
              title={label}
            >
              <Icon size={14} />
              <span>{label}</span>
            </button>
          ))}
        </div>

        {hasImages && (
          <div className="viewer-file-reload">
            <label htmlFor="dicom-reload" className="btn-text-sm">
              <FiUploadCloud size={12} /> Reload
            </label>
            <input
              id="dicom-reload"
              type="file"
              multiple
              webkitdirectory=""
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </div>
        )}
      </div>

      {/* ── Viewport ── */}
      <div className="viewport-wrapper">
        <div
          ref={divRef}
          className="cornerstone-viewport"
          style={{ width: '100%', height: '100%' }}
        />

        {/* Placeholder when no images */}
        {!hasImages && !loading && (
          <div className="viewport-placeholder">
            <FiUploadCloud size={40} className="placeholder-icon" />
            <p className="placeholder-title">No images loaded</p>
            <p className="placeholder-sub">Select a folder of DICOM (.dcm) files to begin</p>
            <label htmlFor="dicom-folder-input" className="btn-load">
              <FiUploadCloud size={16} /> Load DICOM Folder
            </label>
            <input
              id="dicom-folder-input"
              type="file"
              multiple
              webkitdirectory=""
              accept=".dcm"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </div>
        )}

        {/* Loading overlay */}
        {loading && (
          <div className="viewport-loading">
            <div className="loading-spinner" />
            <span>Loading DICOM series…</span>
          </div>
        )}

        {/* Slice counter overlay */}
        {hasImages && (
          <div className="viewer-overlay">
            <span className="overlay-slice">
              {displayIndex} / {displayTotal}
            </span>
            <span className="overlay-hint">Scroll · W/L drag</span>
          </div>
        )}
      </div>

      {/* ── Bottom nav ── */}
      {hasImages && (
        <div className="viewer-nav">
          <button
            className="nav-btn"
            onClick={() => goToSlice(localIndex - 1)}
            disabled={localIndex === 0}
          >
            <FiChevronLeft size={16} /> Prev
          </button>
          <input
            type="range"
            className="slice-slider"
            min={0}
            max={Math.max(0, imageIdsRef.current.length - 1)}
            value={localIndex}
            onChange={(e) => goToSlice(Number(e.target.value))}
          />
          <button
            className="nav-btn"
            onClick={() => goToSlice(localIndex + 1)}
            disabled={localIndex >= imageIdsRef.current.length - 1}
          >
            Next <FiChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
