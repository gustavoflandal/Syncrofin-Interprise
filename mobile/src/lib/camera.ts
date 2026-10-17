import { Capacitor } from '@capacitor/core'
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera'
import { base64ToBlob } from '@/lib/base64'

/** In a browser (development, tests): the file picker, opened on the camera on a phone. */
function pickFromBrowser(): Promise<Blob | null> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.setAttribute('capture', 'environment')
    input.onchange = () => resolve(input.files?.[0] ?? null)
    input.oncancel = () => resolve(null)
    input.click()
  })
}

/**
 * Photograph a receipt. Null when the person cancels the camera, which is not an error.
 *
 * Base64 rather than a file URI: reading a URI back would go through fetch, and on the phone
 * fetch is the native HTTP layer, which is for the server, not for local files.
 */
export async function takeReceiptPhoto(): Promise<Blob | null> {
  if (!Capacitor.isNativePlatform()) return pickFromBrowser()
  try {
    const photo = await Camera.getPhoto({
      quality: 85,
      resultType: CameraResultType.Base64,
      source: CameraSource.Camera,
      correctOrientation: true,
      saveToGallery: false, // a receipt is financial data: keep it out of the phone's gallery
    })
    if (!photo.base64String) return null
    return base64ToBlob(photo.base64String, `image/${photo.format === 'png' ? 'png' : 'jpeg'}`)
  } catch (error) {
    // The plugin rejects when the person backs out of the camera.
    if (error instanceof Error && /cancel/i.test(error.message)) return null
    throw error
  }
}
