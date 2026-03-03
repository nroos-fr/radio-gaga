import React, { useMemo } from 'react';
import { FiLayers, FiImage } from 'react-icons/fi';
import '../styles/SeriesPanel.css';

export default function SeriesPanel({ files, current, total }) {
  const hasFiles = files && files.length > 0;

  // Build a compact list: show up to 50 entries, with ellipsis if more
  const displayFiles = useMemo(() => {
    if (!files || !files.length) return [];
    if (files.length <= 50) return files.map((name, i) => ({ name, index: i + 1 }));
    // Sample evenly
    const step = Math.floor(files.length / 50);
    return files
      .filter((_, i) => i % step === 0)
      .slice(0, 50)
      .map((name, i) => ({ name, index: i * step + 1 }));
  }, [files]);

  const progress = total > 0 ? Math.round(((current - 1) / (total - 1)) * 100) : 0;

  return (
    <div className="series-panel">
      <div className="panel-header">
        <FiLayers size={16} className="panel-icon" />
        <span className="panel-title">Series</span>
        {hasFiles && (
          <span className="panel-badge">
            {total} slice{total !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {!hasFiles ? (
        <div className="series-empty">
          <FiImage size={24} className="empty-icon" />
          <p>No series loaded</p>
        </div>
      ) : (
        <>
          {/* Progress bar */}
          <div className="series-progress-wrap">
            <div className="series-progress-bar">
              <div
                className="series-progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="series-progress-label">
              Slice {current} of {total}
            </span>
          </div>

          {/* File list */}
          <div className="series-list">
            {displayFiles.map(({ name, index }) => (
              <div
                key={name}
                className={`series-item ${index === current ? 'series-item-active' : ''}`}
              >
                <span className="series-index">{String(index).padStart(3, '0')}</span>
                <span className="series-name">{name}</span>
                {index === current && <span className="series-dot" />}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
