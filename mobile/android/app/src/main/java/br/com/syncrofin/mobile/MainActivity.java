package br.com.syncrofin.mobile;

import android.content.pm.ApplicationInfo;
import android.os.Bundle;
import android.view.WindowManager;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Plugins written for this app are registered before the bridge starts.
        registerPlugin(ReceiptOcrPlugin.class);
        super.onCreate(savedInstanceState);
        // Financial data: no screenshots, and the app switcher shows a blank card instead of the screen.
        // Not in debug builds, so the screens can be captured for the manual and for bug reports.
        boolean debuggable = (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
        if (!debuggable) {
            getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE);
        }
    }
}
