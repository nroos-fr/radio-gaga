import * as cornerstone from '@cornerstonejs/core';
import * as cornerstoneTools from '@cornerstonejs/tools';
import cornerstoneDICOMImageLoader from '@cornerstonejs/dicom-image-loader';

let initialized = false;

export async function initCornerstoneServices() {
  if (initialized) return;
  initialized = true; // guard against concurrent calls (React StrictMode)

  // 1. Core must be initialised first (sets up webWorkerManager etc.)
  await cornerstone.init();

  // 2. DICOM image loader — registers dicomfile:/wadouri:/dicomweb: schemes
  //    and spins up the decode web-worker
  cornerstoneDICOMImageLoader.init({ maxWebWorkers: 1 });

  // 3. Tools
  cornerstoneTools.init();
}

export { cornerstone, cornerstoneTools, cornerstoneDICOMImageLoader };
