import React, { useState, useRef } from 'react';
import { FiFileText, FiChevronDown, FiChevronUp, FiEdit3, FiCopy, FiCheck, FiDownload, FiNavigation } from 'react-icons/fi';
import '../styles/ReportPanel.css';

function buildMarkdown(reportData) {
  const lines = [];
  lines.push('# Radiology Report');
  lines.push('');
  lines.push(`| | |`);
  lines.push(`|---|---|`);
  lines.push(`| **Patient** | ${reportData.patientName} |`);
  if (reportData.patientSex)  lines.push(`| **Sex** | ${reportData.patientSex} |`);
  if (reportData.patientAge != null) lines.push(`| **Age** | ${reportData.patientAge} y |`);
  lines.push(`| **Date** | ${reportData.studyDate} |`);
  lines.push(`| **Modality** | ${reportData.modality} |`);
  lines.push('');

  if (reportData.reasons_for_study) {
    lines.push('## Reasons for Study');
    lines.push(reportData.reasons_for_study);
    lines.push('');
  }
  if (reportData.study_technique) {
    lines.push('## Study Technique');
    lines.push(reportData.study_technique);
    lines.push('');
  }
  const validated = reportData.statements?.filter(s => s.checked) ?? [];
  if (validated.length) {
    lines.push('## Statements');
    for (const s of validated) {
      lines.push(`- ${s.text}`);
    }
    lines.push('');
  }
  if (reportData.conclusion) {
    lines.push('## Conclusion');
    lines.push(reportData.conclusion);
    lines.push('');
  }

  return lines.join('\n');
}

function buildHtml(reportData) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const metaRows = [
    ['Patient', reportData.patientName],
    reportData.patientSex ? ['Sex', reportData.patientSex] : null,
    reportData.patientAge != null ? ['Age', `${reportData.patientAge} y`] : null,
    ['Date', reportData.studyDate],
    ['Modality', reportData.modality],
  ].filter(Boolean);

  const validatedHtml = (reportData.statements ?? []).filter(s => s.checked);
  const statementsHtml = validatedHtml.length
    ? `<h2>Statements</h2><ul class="statements">${validatedHtml.map(s =>
        `<li class="checked"><span class="cb">✓</span>${esc(s.text)}</li>`
      ).join('')}</ul>`
    : '';

  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Radiology Report — ${esc(reportData.patientName)}</title>
<style>
  body { font-family: Georgia, serif; font-size: 13px; color: #1a1a2e; margin: 0; padding: 32px 48px; }
  h1 { font-size: 20px; border-bottom: 2px solid #2563eb; padding-bottom: 8px; color: #1e3a8a; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: #2563eb;
       margin: 20px 0 6px; border-bottom: 1px solid #dbeafe; padding-bottom: 4px; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 12px; }
  td { padding: 4px 8px; border: 1px solid #e2e8f0; }
  td:first-child { font-weight: 600; color: #475569; width: 90px; }
  p { margin: 4px 0 0; line-height: 1.6; }
  ul.statements { list-style: none; padding: 0; margin: 0; }
  ul.statements li { display: flex; gap: 10px; padding: 5px 0; border-bottom: 1px solid #f1f5f9; line-height: 1.5; }
  ul.statements li:last-child { border-bottom: none; }
  .cb { flex-shrink: 0; font-size: 14px; color: #94a3b8; }
  .checked .cb { color: #22c55e; }
  .checked { color: #16a34a; }
  @media print { body { padding: 20px 32px; } }
</style></head><body>
<h1>Radiology Report</h1>
<table>${metaRows.map(([l, v]) => `<tr><td>${esc(l)}</td><td>${esc(String(v))}</td></tr>`).join('')}</table>
${reportData.reasons_for_study ? `<h2>Reasons for Study</h2><p>${esc(reportData.reasons_for_study)}</p>` : ''}
${reportData.study_technique   ? `<h2>Study Technique</h2><p>${esc(reportData.study_technique)}</p>`   : ''}
${statementsHtml}
${reportData.conclusion        ? `<h2>Conclusion</h2><p>${esc(reportData.conclusion)}</p>`              : ''}
</body></html>`;
}

const TEXT_SECTIONS_TOP = [
  {
    key: 'reasons_for_study',
    label: 'Reasons for Study',
    placeholder: 'Clinical indication for this examination…',
  },
  {
    key: 'study_technique',
    label: 'Study Technique',
    placeholder: 'Acquisition protocol, contrast, comparison exam…',
  },
];

const CONCLUSION_SECTION = {
  key: 'conclusion',
  label: 'Conclusion',
  placeholder: 'RECIST 1.1 category and one-sentence justification…',
};

function TextSection({ title, value, placeholder, editMode, onChange }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="report-section">
      <button className="report-section-header" onClick={() => setExpanded(v => !v)}>
        <span className="section-title">{title}</span>
        {expanded ? <FiChevronUp size={14} /> : <FiChevronDown size={14} />}
      </button>
      {expanded && (
        editMode ? (
          <textarea
            className="report-textarea"
            value={value}
            placeholder={placeholder}
            onChange={e => onChange(e.target.value)}
            rows={3}
          />
        ) : (
          <p className="report-text">{value || <span className="report-empty">—</span>}</p>
        )
      )}
    </div>
  );
}

const IMAGE_RE = /\b(image\s+(\d+))\b/gi;

function StatementText({ text, onJumpToSlice }) {
  if (!text) return null;
  const parts = [];
  let last = 0;
  let match;
  IMAGE_RE.lastIndex = 0;
  while ((match = IMAGE_RE.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const sliceN = parseInt(match[2], 10);
    parts.push(
      <button
        key={match.index}
        className="statement-img-link"
        onClick={() => onJumpToSlice?.(sliceN)}
        title={`Jump to image ${sliceN}`}
      >
        {match[1]}
      </button>
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

function StatementsSection({ statements, editMode, onToggle, onEdit, onAdd, onDelete, onJumpToSlice }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="report-section">
      <button className="report-section-header" onClick={() => setExpanded(v => !v)}>
        <span className="section-title">Statements</span>
        {expanded ? <FiChevronUp size={14} /> : <FiChevronDown size={14} />}
      </button>
      {expanded && (
        <ul className="statements-list">
          {statements.length === 0 && (
            <li className="statement-empty">No findings recorded.</li>
          )}
          {statements.map((s, i) => (
            <li key={i} className={`statement-item${s.checked ? ' statement-checked' : ''}`}>
              <input
                type="checkbox"
                className="statement-checkbox"
                checked={!!s.checked}
                onChange={() => onToggle(i)}
              />
              {editMode ? (
                <input
                  type="text"
                  className="statement-input"
                  value={s.text}
                  onChange={e => onEdit(i, e.target.value)}
                />
              ) : (
                <span className="statement-text">
                  <StatementText text={s.text} onJumpToSlice={onJumpToSlice} />
                </span>
              )}
              {s.slice_index != null && onJumpToSlice && (
                <button
                  className="statement-slice-link"
                  onClick={() => onJumpToSlice(s.slice_index)}
                  title={`Jump to slice ${s.slice_index}`}
                >
                  <FiNavigation size={11} />
                  <span>#{s.slice_index}</span>
                </button>
              )}
              {editMode && (
                <button className="statement-delete" onClick={() => onDelete(i)} title="Remove">
                  ×
                </button>
              )}
            </li>
          ))}
          {editMode && (
            <li className="statement-add">
              <button className="btn-add-statement" onClick={onAdd}>+ Add finding</button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

export default function ReportPanel({ reportData, onReportChange, onJumpToSlice }) {
  const [editMode,  setEditMode]  = useState(false);
  const [copied,    setCopied]    = useState(false);

  const hasReport = !!(
    reportData.reasons_for_study ||
    reportData.study_technique   ||
    reportData.statements?.length ||
    reportData.conclusion
  );
  const printFrameRef = useRef(null);

  const handleCopy = () => {
    navigator.clipboard.writeText(buildMarkdown(reportData)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handlePdf = () => {
    const html = buildHtml(reportData);
    let frame = printFrameRef.current;
    if (!frame) {
      frame = document.createElement('iframe');
      frame.style.cssText = 'position:fixed;width:0;height:0;border:none;opacity:0;pointer-events:none;';
      document.body.appendChild(frame);
      printFrameRef.current = frame;
    }
    const doc = frame.contentDocument || frame.contentWindow.document;
    doc.open();
    doc.write(html);
    doc.close();
    frame.contentWindow.focus();
    setTimeout(() => frame.contentWindow.print(), 250);
  };

  const handleToggle = i => {
    const updated = reportData.statements.map((s, idx) =>
      idx === i ? { ...s, checked: !s.checked } : s
    );
    onReportChange('statements', updated);
  };

  const handleEdit = (i, text) => {
    const updated = reportData.statements.map((s, idx) =>
      idx === i ? { ...s, text } : s
    );
    onReportChange('statements', updated);
  };

  const handleAdd = () => {
    onReportChange('statements', [...reportData.statements, { text: '', checked: false }]);
  };

  const handleDelete = i => {
    onReportChange('statements', reportData.statements.filter((_, idx) => idx !== i));
  };

  return (
    <div className="report-panel">
      <div className="panel-header">
        <div className="panel-header-left">
          <FiFileText size={16} className="panel-icon" />
          <span className="panel-title">Radiology Report</span>
        </div>
        {hasReport && (
          <div className="panel-header-actions">
            <button
              className={`btn-icon${copied ? ' btn-icon-copied' : ''}`}
              title="Copy report as Markdown"
              onClick={handleCopy}
            >
              {copied ? <FiCheck size={14} /> : <FiCopy size={14} />}
              <span>{copied ? 'Copied!' : 'Copy MD'}</span>
            </button>
            <button
              className="btn-icon"
              title="Export report as PDF"
              onClick={handlePdf}
            >
              <FiDownload size={14} />
              <span>PDF</span>
            </button>
            <button
              className={`btn-icon ${editMode ? 'btn-icon-active' : ''}`}
              title={editMode ? 'Lock report' : 'Edit report'}
              onClick={() => setEditMode(v => !v)}
            >
              <FiEdit3 size={14} />
              <span>{editMode ? 'Editing' : 'Edit'}</span>
            </button>
          </div>
        )}
      </div>

      <div className="report-meta">
        <div className="meta-row">
          <span className="meta-label">Patient</span>
          <span className="meta-value">{reportData.patientName}</span>
        </div>
        <div className="meta-row">
          <span className="meta-label">Date</span>
          <span className="meta-value">{reportData.studyDate}</span>
        </div>
        <div className="meta-row">
          <span className="meta-label">Modality</span>
          <span className="meta-value">{reportData.modality}</span>
        </div>
        {reportData.patientSex && (
          <div className="meta-row">
            <span className="meta-label">Sex</span>
            <span className="meta-value">{reportData.patientSex}</span>
          </div>
        )}
        {reportData.patientAge != null && (
          <div className="meta-row">
            <span className="meta-label">Age</span>
            <span className="meta-value">{reportData.patientAge} y</span>
          </div>
        )}
      </div>

      <div className="report-divider" />

      <div className="report-body">
        {TEXT_SECTIONS_TOP.map(({ key, label, placeholder }) => (
          <TextSection
            key={key}
            title={label}
            value={reportData[key]}
            placeholder={placeholder}
            editMode={editMode}
            onChange={val => onReportChange(key, val)}
          />
        ))}
        <StatementsSection
          statements={reportData.statements}
          editMode={editMode}
          onToggle={handleToggle}
          onEdit={handleEdit}
          onAdd={handleAdd}
          onDelete={handleDelete}
          onJumpToSlice={onJumpToSlice}
        />
        <TextSection
          key={CONCLUSION_SECTION.key}
          title={CONCLUSION_SECTION.label}
          value={reportData[CONCLUSION_SECTION.key]}
          placeholder={CONCLUSION_SECTION.placeholder}
          editMode={editMode}
          onChange={val => onReportChange(CONCLUSION_SECTION.key, val)}
        />
      </div>

      <div className="report-footer">
        <span className="footer-note">
          Auto-populated from DICOM headers · Edit freely
        </span>
        {reportData.reportSource && (
          <span className="report-source-badge" data-source={reportData.reportSource}>
            ?
            <span className="report-source-tooltip">
              {reportData.reportSource === 'template'
                ? 'This report was generated from a template using measured lesion data. It does not reflect a real AI analysis.'
                : 'This report was generated by AI and may contain errors or false information. Always verify with a qualified radiologist.'}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}
