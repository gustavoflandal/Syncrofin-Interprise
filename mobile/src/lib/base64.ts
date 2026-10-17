/** Shared by anything that moves an image between a `Blob` and the base64 strings the Camera
 * and Filesystem plugins speak. */

export function base64ToBlob(base64: string, type: string): Blob {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type })
}

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      // "data:<type>;base64,<data>" — only the part after the comma is the encoded bytes.
      const result = reader.result as string
      resolve(result.slice(result.indexOf(',') + 1))
    }
    reader.onerror = () => reject(reader.error ?? new Error('failed to read blob'))
    reader.readAsDataURL(blob)
  })
}
