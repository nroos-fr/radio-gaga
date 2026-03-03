import React, { useState, useMemo } from 'react';
import { FiInfo, FiTag, FiChevronDown, FiChevronRight } from 'react-icons/fi';
import '../styles/MetadataPanel.css';

// DICOM tag definitions to display
const TAG_DEFS = [
  { tag: 'x00080060', label: 'Modality' },
  { tag: 'x00100010', label: 'Patient Name' },
  { tag: 'x00100020', label: 'Patient ID' },
  { tag: 'x00100030', label: 'Birth Date' },
  { tag: 'x00100040', label: 'Sex' },
  { tag: 'x00080020', label: 'Study Date' },
  { tag: 'x00080030', label: 'Study Time' },
  { tag: 'x0008103e', label: 'Series Description' },
  { tag: 'x00080080', label: 'Institution' },
  { tag: 'x00181030', label: 'Protocol' },
  { tag: 'x00200013', label: 'Instance Number' },
  { tag: 'x00200037', label: 'Image Orientation' },
  { tag: 'x00280010', label: 'Rows' },
  { tag: 'x00280011', label: 'Columns' },
  { tag: 'x00280030', label: 'Pixel Spacing' },
  { tag: 'x00180050', label: 'Slice Thickness' },
  { tag: 'x00281050', label: 'Window Center' },
  { tag: 'x00281051', label: 'Window Width' },
  { tag: 'x00280100', label: 'Bits Allocated' },
];

function safeString(dataset, tag) {
  if (!dataset) return null;
  try {
    const val = dataset.string(tag);
    return val && val.trim() ? val.trim() : null;
  } catch {
    return null;
  }
}

function formatTime(raw) {
  if (!raw || raw.length < 4) return raw;
  return `${raw.slice(0, 2)}:${raw.slice(2, 4)}`;
}

function formatDate(raw) {
  if (!raw || raw.length < 8) return raw;
  return `${raw.slice(6, 8)}/${raw.slice(4, 6)}/${raw.slice(0, 4)}`;
}

export default function MetadataPanel({ metadata }) {
  const [isOpen, setIsOpen] = useState(false);

  const rows = useMemo(() => {
    if (!metadata) return [];
    return TAG_DEFS.map(({ tag, label }) => {
      let val = safeString(metadata, tag);
      if (val && tag === 'x00080020') val = formatDate(val);
      if (val && tag === 'x00100030') val = formatDate(val);
      if (val && tag === 'x00080030') val = formatTime(val);
      return { label, value: val };
    }).filter((r) => r.value !== null);
  }, [metadata]);

  return (
    <div className="metadata-panel">
      <button
        className="panel-header metadata-toggle"
        onClick={() => setIsOpen((o) => !o)}
        aria-expanded={isOpen}
      >
        <FiInfo size={16} className="panel-icon" />
        <span className="panel-title">Image Metadata</span>
        {metadata && <span className="panel-badge">{rows.length} tags</span>}
        <span className="metadata-chevron">
          {isOpen ? <FiChevronDown size={14} /> : <FiChevronRight size={14} />}
        </span>
      </button>

      {isOpen && (
        <div className="metadata-body">
          {!metadata ? (
            <div className="metadata-empty">
              <FiTag size={24} className="empty-icon" />
              <p>Load a DICOM series to see image metadata</p>
            </div>
          ) : (
            <div className="metadata-table">
              {rows.map(({ label, value }) => (
                <div className="metadata-row" key={label}>
                  <span className="meta-key">{label}</span>
                  <span className="meta-val">{value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
