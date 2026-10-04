package io.concurse.desktop

import android.os.Bundle
import android.util.Log
import androidx.activity.enableEdgeToEdge
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : TauriActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        startProcessingEngine()
    }

    private fun startProcessingEngine() {
        if (!engineStarted.compareAndSet(false, true)) return
        val context = applicationContext
        Thread({
            try {
                if (!Python.isStarted()) Python.start(AndroidPlatform(context))
                val processingDir = File(context.filesDir, "processing").absolutePath
                Python.getInstance().getModule("mobile_engine").callAttr(
                    "run", processingDir, BuildConfig.CONCURSE_SUPABASE_URL,
                    BuildConfig.CONCURSE_SUPABASE_PUBLISHABLE_KEY, context
                )
            } catch (error: Throwable) {
                // A failed engine must leave the app open and report readiness
                // failure to the import flow instead of aborting the WebView.
                Log.e("ConcurseEngine", "Processing engine failed to start", error)
                engineStarted.set(false)
            }
        }, "concurse-processing-engine").apply { isDaemon = true; start() }
    }

    companion object {
        private val engineStarted = AtomicBoolean(false)
    }
}
