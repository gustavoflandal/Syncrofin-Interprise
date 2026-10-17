const MAX_SIDE = 1600
const QUALITY = 0.82
/** Below this a photo is already small enough; re-encoding would only lose quality. */
const SKIP_BELOW_BYTES = 400 * 1024

/**
 * A phone photo is 3 to 8 MB and the server accepts 10 MB. Scale it so the longest side is
 * 1600 px (enough to read a receipt) and re-encode as JPEG: about 300 KB, which uploads fast
 * on mobile data. Returns the original when it cannot do better.
 */
export async function shrinkPhoto(blob: Blob): Promise<Blob> {
  if (blob.size < SKIP_BELOW_BYTES || typeof createImageBitmap !== 'function') return blob
  try {
    const bitmap = await createImageBitmap(blob, { imageOrientation: 'from-image' })
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    const smaller = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', QUALITY))
    return smaller && smaller.size < blob.size ? smaller : blob
  } catch {
    return blob
  }
}

export function receiptFilename(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  return `comprovante-${stamp}.jpg`
}
