import { Capacitor, registerPlugin } from '@capacitor/core'
import { parseReceipt, type OcrResult, type ReceiptSuggestion } from '@/lib/receipt-parser'

/** The native side: ML Kit text recognition on the phone (android/.../ReceiptOcrPlugin.java). */
interface ReceiptOcrPlugin {
  recognize(options: { base64: string }): Promise<OcrResult>
}

const ReceiptOcr = registerPlugin<ReceiptOcrPlugin>('ReceiptOcr')

/** Only the Android app has the recognizer; in a browser (development, tests) there is nothing to offer. */
export function ocrAvailable(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('ReceiptOcr')
}

function toBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

/**
 * Suggestions read from a receipt photo, or null when the reading failed. Run it on the photo as
 * the camera delivered it, not on the shrunk upload: more pixels, better text. The image never
 * leaves the phone for this.
 */
export async function readReceipt(photo: Blob): Promise<ReceiptSuggestion | null> {
  try {
    const result = await ReceiptOcr.recognize({ base64: await toBase64(photo) })
    // For tuning the reader against real receipts (adb logcat / remote inspector). Off unless asked for.
    if (localStorage.getItem('syncrofin_debug_ocr') === '1') console.log('[ocr]', JSON.stringify(result))
    return parseReceipt(result)
  } catch {
    return null
  }
}
