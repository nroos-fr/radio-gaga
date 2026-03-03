import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import Header from './components/Header';
import ReportPanel from './components/ReportPanel';
import MultiViewer from './components/MultiViewer';
import MetadataPanel from './components/MetadataPanel';
import SeriesPanel from './components/SeriesPanel';
import PngScroller from './components/PngScroller';
import './styles/App.css';

const DEFAULT_STUDY_ID = 'PATIENT001 PATIENT001/STUDY0001 TC TRAX TC ABDOMEN TC PELVIS';

export default function App() {
  // ── DICOM / report state ────────────────────────────────────────────────
  const [dicomMetadata, setDicomMetadata] = useState(null);
  const [isLoadingLesions, setIsLoadingLesions] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeMsg, setAnalyzeMsg] = useState('');
  const [selectedStudy, setSelectedStudy] = useState(DEFAULT_STUDY_ID);
  const [seriesInfo, setSeriesInfo] = useState({ total: 0, current: 0, files: [] });
  const [reportData, setReportData] = useState({
    patientName: '—', studyDate: '—', modality: '—',
    patientSex: '', patientAge: null,
    reasons_for_study: '', study_technique: '', statements: [], conclusion: '',
    reportSource: null,
  });

  // ── Patients list (for "next study" button) ─────────────────────────────
  const [patients, setPatients] = useState([]);
  useEffect(() => {
    fetch('/api/patients')
      .then(r => r.json())
      .then(d => setPatients(d.patients ?? []))
      .catch(() => { });
  }, []);

  // ── Analysis / PNG state ────────────────────────────────────────────────
  const [analysisResult, setAnalysisResult] = useState(null);
  const [showPngMask, setShowPngMask] = useState(true);
  const [pngJumpTo, setPngJumpTo] = useState(null);
  const [imagesBaseUrl, setImagesBaseUrl] = useState(null);
  const viewerRef = useRef(null);

  // ── Derived ─────────────────────────────────────────────────────────────
  const showPngScroller = analysisResult?.status === 'ok';

  // Studies for the current patient (used by "next study" button)
  const currentStudies = useMemo(() => {
    const p = patients.find(p2 => p2.studies.some(s => s.study_id === selectedStudy));
    return p?.studies ?? [];
  }, [patients, selectedStudy]);

  // ── Core logic ───────────────────────────────────────────────────────────
  const runDetectLesions = useCallback(async (studyId) => {
    setIsLoadingLesions(true);
    try {
      const encoded = studyId.split('/').map(encodeURIComponent).join('/');
      const res = await fetch(`/api/lesions/${encoded}`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'ok') {
        setAnalysisResult(data);
        setImagesBaseUrl(data.images_base_url ?? null);
        setReportData(prev => ({
          ...prev,
          patientSex: data.patient_sex ?? '',
          patientAge: data.patient_age ?? null,
        }));
      } else {
        setAnalysisResult(null);
      }
      return data;
    } catch (err) {
      console.error('[lesions]', err);
      setAnalysisResult(null);
    } finally {
      setIsLoadingLesions(false);
    }
  }, []);

  // Auto-detect lesions whenever the selected study changes
  useEffect(() => {
    setPngJumpTo(null);
    runDetectLesions(selectedStudy);
  }, [selectedStudy]); // eslint-disable-line react-hooks/exhaustive-deps

  const runGenerateReport = useCallback(async (studyId) => {
    const encoded = studyId.split('/').map(encodeURIComponent).join('/');
    const res = await fetch(`/api/report/${encoded}`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      setReportData(prev => ({
        ...prev,
        reasons_for_study: data.report.reasons_for_study ?? '',
        study_technique: data.report.study_technique ?? '',
        statements: data.report.statements ?? [],
        conclusion: data.report.conclusion ?? '',
        reportSource: data.report_source ?? 'ai',
      }));
    }
    return data;
  }, []);

  // ── Button handler ────────────────────────────────────────────────────────
  const handleAnalyze = useCallback(async () => {
    setAnalyzeMsg('');
    setIsAnalyzing(true);
    try {
      setAnalyzeMsg('Generating report…');
      await runGenerateReport(selectedStudy);
      setAnalyzeMsg('Done.');
    } catch (err) {
      console.error('[analyze]', err);
      setAnalyzeMsg('An error occurred during analysis.');
    } finally {
      setIsAnalyzing(false);
    }
  }, [selectedStudy, runGenerateReport]);

  const resetAnalysis = useCallback(() => {
    setAnalysisResult(null);
    setImagesBaseUrl(null);
    setPngJumpTo(null);
    setAnalyzeMsg('');
    setIsAnalyzing(false);
    setReportData(prev => ({ ...prev, patientSex: '', patientAge: null, reasons_for_study: '', study_technique: '', statements: [], conclusion: '', reportSource: null }));
  }, []);

  // Jump both viewers to a specific slice (torax series, 0-based index)
  const handleJumpToSlice = useCallback((sliceIndex) => {
    viewerRef.current?.goToSlice('torax', sliceIndex);
    setPngJumpTo(sliceIndex);
  }, []);

  // PngScroller scrolled — sync the DICOM viewer
  const handlePngSliceChange = useCallback((sliceIndex) => {
    viewerRef.current?.goToSlice('torax', sliceIndex);
  }, []);

  const handleNextStudy = useCallback(() => {
    if (!currentStudies.length) return;
    const idx = currentStudies.findIndex(s => s.study_id === selectedStudy);
    const next = currentStudies[(idx + 1) % currentStudies.length];
    setSelectedStudy(next.study_id);
    setDicomMetadata(null);
    resetAnalysis();
  }, [currentStudies, selectedStudy, resetAnalysis]);

  // ── Cornerstone callbacks ────────────────────────────────────────────────
  const handleMetadataUpdate = useCallback((metadata, imageIndex) => {
    setDicomMetadata(metadata);
    if (metadata) {
      const getString = tag => { try { return metadata.string(tag) || '—'; } catch { return '—'; } };
      setReportData(prev => ({
        ...prev,
        patientName: getString('x00100010'),
        studyDate: formatDate(getString('x00080020')),
        modality: getString('x00080060'),
      }));
    }
    setSeriesInfo(prev => ({ ...prev, current: imageIndex + 1 }));
  }, []);

  const handleSeriesLoad = useCallback((fileNames) => {
    setSeriesInfo(prev => ({ ...prev, total: fileNames.length, current: 1, files: fileNames }));
  }, []);

  return (
    <div className="app">
      <Header
        patientName={reportData.patientName}
        studyDate={reportData.studyDate}
        modality={reportData.modality}
        selectedStudy={selectedStudy}
        onStudyChange={(id) => { setSelectedStudy(id); setDicomMetadata(null); resetAnalysis(); }}
      />
      <main className="dashboard">
        {/* ── LEFT — PNG scroller + Report ── */}
        <aside className="panel panel-left">
          {showPngScroller && (
            <PngScroller
              examData={analysisResult}
              showMask={showPngMask}
              jumpTo={pngJumpTo}
              imagesBaseUrl={imagesBaseUrl}
              onSliceChange={handlePngSliceChange}
            />
          )}
          <div className="report-wrap">
            <ReportPanel
              reportData={reportData}
              onReportChange={(field, value) =>
                setReportData(prev => ({ ...prev, [field]: value }))
              }
              onJumpToSlice={handleJumpToSlice}
            />
          </div>
        </aside>

        {/* ── RIGHT — Viewer + Info panels ── */}
        <section className="panel-right">
          {/* DICOM viewer */}
          <div className="block block-viewer">
            <MultiViewer
              ref={viewerRef}
              key={selectedStudy}
              studyId={selectedStudy}
              lesions={analysisResult?.lesions ?? []}
              showPngMask={showPngMask}
              onTogglePngMask={() => setShowPngMask(v => !v)}
              onJumpToLesion={handleJumpToSlice}
              onMetadataUpdate={handleMetadataUpdate}
              onSeriesLoad={handleSeriesLoad}
              onSliceChange={setPngJumpTo}
            />
          </div>

          {/* Analyze + next-study bar */}
          <div className="analyze-bar">
            <button
              className={`analyze-btn${(isAnalyzing || isLoadingLesions) ? ' analyze-btn--busy' : ''}`}
              onClick={handleAnalyze}
              disabled={isAnalyzing || isLoadingLesions}
            >
              {isLoadingLesions
                ? <><span className="analyze-spinner" /> Loading lesions…</>
                : isAnalyzing
                  ? <><span className="analyze-spinner" /> Generating report…</>
                  : '🔬 Generate report'}
            </button>

            {currentStudies.length > 0 && (
              <button className="next-study-btn" onClick={handleNextStudy} disabled={isAnalyzing}>
                Next study →
              </button>
            )}

            {analyzeMsg && <span className="analyze-msg">{analyzeMsg}</span>}
          </div>

          {/* Bottom row */}
          <div className="blocks-bottom">
            <div className="block block-metadata">
              <MetadataPanel metadata={dicomMetadata} />
            </div>
            <div className="block block-series">
              <SeriesPanel
                files={seriesInfo.files}
                current={seriesInfo.current}
                total={seriesInfo.total}
              />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function formatDate(raw) {
  if (!raw || raw === '—' || raw.length < 8) return raw;
  return `${raw.slice(6, 8)}/${raw.slice(4, 6)}/${raw.slice(0, 4)}`;
}

