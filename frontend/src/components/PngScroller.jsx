import React, { useState, useEffect, useRef } from 'react';
import '../styles/PngScroller.css';

/**
 * PngScroller — shows CT slices as PNG images.
 * Props:
 *   examData      { exam_index, lesions, slice_count }  from /api/analyze response
 *   showMask      boolean — show with_seg variant for slices that have it
 *   jumpTo        slice index to jump to (e.g. lesion center)
 *   imagesBaseUrl base URL for PNG assets, e.g. "/data/mock_data" or "/data/PATIENT001"
 */
export default function PngScroller({ examData, showMask, jumpTo, imagesBaseUrl = null, onSliceChange }) {
  const [sliceIdx, setSliceIdx] = useState(0);
  const prevJumpRef = useRef(undefined);

  const { exam_index = 0, lesions = [], slice_count = 1 } = examData ?? {};
  const examStr = String(exam_index).padStart(4, '0');
  const total = Math.max(1, slice_count);

  // Reset to first slice when exam changes
  useEffect(() => {
    setSliceIdx(0);
    prevJumpRef.current = undefined;
  }, [exam_index]);

  // Jump to a specific slice when requested externally
  useEffect(() => {
    if (jumpTo != null && jumpTo !== prevJumpRef.current) {
      prevJumpRef.current = jumpTo;
      setSliceIdx(Math.max(0, Math.min(jumpTo, total - 1)));
    }
  }, [jumpTo, total]);

  // Notify parent whenever the slice changes (for DICOM viewer sync)
  useEffect(() => {
    onSliceChange?.(sliceIdx);
  }, [sliceIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  const sliceStr = String(sliceIdx).padStart(4, '0');

  // Does the current slice have a segmentation overlay?
  const hasSeg = lesions.some(l => sliceIdx >= (l.slice_min ?? 0) && sliceIdx <= (l.slice_max ?? 0));
  const useSegImg = showMask && hasSeg;

  const imgSrc = useSegImg
    ? `${imagesBaseUrl}/images_with_seg/exam_${examStr}/exam_${examStr}__slice_${sliceStr}__with_seg.png`
    : `${imagesBaseUrl}/images_ct_only/exam_${examStr}/exam_${examStr}__slice_${sliceStr}__ct_only.png`;

  return (
    <div className="png-scroller">
      <div className="png-scroller-imgwrap">
        <img src={imgSrc} alt={`Slice ${sliceIdx}`} className="png-scroller-img" />
        <span className="png-scroller-badge">
          {sliceIdx}&thinsp;/&thinsp;{total - 1}
          {useSegImg && <span className="png-badge-seg">SEG</span>}
        </span>
      </div>

      <div className="png-scroller-nav">
        <button
          className="png-nav-btn"
          onClick={() => setSliceIdx(s => Math.max(0, s - 1))}
          disabled={sliceIdx <= 0}
        >‹</button>

        <input
          type="range"
          min={0}
          max={total - 1}
          value={sliceIdx}
          onChange={e => setSliceIdx(Number(e.target.value))}
          className="png-slider"
        />

        <button
          className="png-nav-btn"
          onClick={() => setSliceIdx(s => Math.min(total - 1, s + 1))}
          disabled={sliceIdx >= total - 1}
        >›</button>
      </div>
    </div>
  );
}
