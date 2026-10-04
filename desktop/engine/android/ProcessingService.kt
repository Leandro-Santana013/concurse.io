package io.concurse.desktop

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import java.util.concurrent.atomic.AtomicInteger

/** Keeps an active PDF extraction alive when the user changes applications. */
class ProcessingService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val channelId = "concurse-processing"
        if (Build.VERSION.SDK_INT >= 26) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(channelId, "Processamento de provas", NotificationManager.IMPORTANCE_LOW)
            )
        }
        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle("concurse.io")
            .setContentText("Processando a prova neste dispositivo")
            .setOngoing(true)
            .build()
        startForeground(45873, notification)
        if (pendingJobs.get() == 0) stopSelf()
        return START_NOT_STICKY
    }

    companion object {
        private val pendingJobs = AtomicInteger(0)

        @JvmStatic fun begin(context: Context) {
            if (pendingJobs.incrementAndGet() == 1) {
                val intent = Intent(context, ProcessingService::class.java)
                try {
                    if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent)
                    else context.startService(intent)
                } catch (error: RuntimeException) {
                    // If Android has already put the app in the background,
                    // leave the working job recoverable on the next opening.
                    pendingJobs.decrementAndGet()
                    android.util.Log.w("ConcurseEngine", "Could not keep processing in foreground", error)
                }
            }
        }

        @JvmStatic fun end(context: Context) {
            if (pendingJobs.updateAndGet { value -> maxOf(0, value - 1) } == 0) {
                context.stopService(Intent(context, ProcessingService::class.java))
            }
        }
    }
}
