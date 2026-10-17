package br.com.syncrofin.mobile;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Base64;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

/**
 * Reads the text of a receipt photo on the phone (ML Kit, bundled Latin model: no network, the
 * image never leaves the device). JS gets the plain text and the lines with their position
 * (top and left, as fractions of the photo), and does the interpretation (amount, date,
 * merchant) itself.
 */
@CapacitorPlugin(name = "ReceiptOcr")
public class ReceiptOcrPlugin extends Plugin {
    /** Longest side handed to the recognizer. A 12 MP photo needs no more to read a receipt. */
    private static final int MAX_SIDE = 2400;

    private TextRecognizer recognizer;

    @PluginMethod
    public void recognize(PluginCall call) {
        String base64 = call.getString("base64");
        if (base64 == null || base64.isEmpty()) {
            call.reject("base64 is required");
            return;
        }
        Bitmap bitmap;
        try {
            byte[] bytes = Base64.decode(base64, Base64.DEFAULT);
            bitmap = decode(bytes);
        } catch (Exception e) {
            call.reject("could not decode the image", e);
            return;
        }
        if (bitmap == null) {
            call.reject("could not decode the image");
            return;
        }
        if (recognizer == null) {
            recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
        }
        final int height = bitmap.getHeight();
        final int width = bitmap.getWidth();
        recognizer
            .process(InputImage.fromBitmap(bitmap, 0))
            .addOnSuccessListener(text -> {
                JSObject result = new JSObject();
                result.put("text", text.getText());
                JSArray lines = new JSArray();
                for (Text.TextBlock block : text.getTextBlocks()) {
                    for (Text.Line line : block.getLines()) {
                        JSObject item = new JSObject();
                        item.put("text", line.getText());
                        android.graphics.Rect box = line.getBoundingBox();
                        item.put("top", box == null ? 0 : (double) box.top / height);
                        item.put("left", box == null ? 0 : (double) box.left / width);
                        lines.put(item);
                    }
                }
                result.put("lines", lines);
                call.resolve(result);
            })
            .addOnFailureListener(e -> call.reject("recognition failed: " + e.getMessage(), e));
    }

    /** Decodes with a sample size so a large photo does not have to fit in memory at full size. */
    private static Bitmap decode(byte[] bytes) {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        int sample = 1;
        while (Math.max(bounds.outWidth, bounds.outHeight) / sample > MAX_SIDE * 2) {
            sample *= 2;
        }
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sample;
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    }

    @Override
    protected void handleOnDestroy() {
        if (recognizer != null) {
            recognizer.close();
        }
    }
}
