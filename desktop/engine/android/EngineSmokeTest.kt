package io.concurse.desktop

import android.content.Intent
import android.view.View
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.chaquo.python.Python
import java.net.HttpURLConnection
import java.net.URL
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

/** Executes the actual packaged PDF/OCR libraries on the connected Android. */
@RunWith(AndroidJUnit4::class)
class EngineSmokeTest {
    @Test fun embeddedProcessingStartsAndReadsNativeAndScannedPdf() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        val deadline = System.currentTimeMillis() + 90000
        var status = 0
        while (System.currentTimeMillis() < deadline) {
            try {
                val connection = URL("http://127.0.0.1:45873/health").openConnection() as HttpURLConnection
                connection.connectTimeout = 1000
                connection.readTimeout = 1000
                status = connection.responseCode
                connection.disconnect()
                if (status == 200) break
            } catch (_: Exception) { }
            Thread.sleep(250)
        }
        assertEquals("O motor Python deve iniciar com as bibliotecas do APK", 200, status)
        instrumentation.runOnMainSync {
            val content = activity.findViewById<View>(android.R.id.content)
            val rootInsets = ViewCompat.getRootWindowInsets(content)
            assertNotNull("A janela deve informar o espaço das barras do Android", rootInsets)
            val expected = rootInsets!!.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            assertEquals("Conteúdo deve respeitar a barra superior", expected.top, content.paddingTop)
            assertEquals("Conteúdo deve respeitar a navegação do Android", expected.bottom, content.paddingBottom)
            assertEquals(expected.left, content.paddingLeft)
            assertEquals(expected.right, content.paddingRight)
        }
        Python.getInstance().getModule("builtins").callAttr("exec", """
import json, os, tempfile
from pathlib import Path
import fitz, numpy as np, cv2
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from services.auth import create_session_token, read_session_token
from services.crawlers import get_ddgs_class
from rapidocr_onnxruntime import RapidOCR
assert os.environ.get('CRYPTOGRAPHY_OPENSSL_NO_LEGACY') == '1'
aes = AESGCM(AESGCM.generate_key(bit_length=256))
nonce = os.urandom(12)
protected = aes.encrypt(nonce, b'android engine', b'concurse')
assert aes.decrypt(nonce, protected, b'concurse') == b'android engine'
assert read_session_token(create_session_token(42)) == 42
ddgs = get_ddgs_class()
assert ddgs is not None, 'O backend de busca deve estar incluido no APK'
with ddgs(timeout=10):
    pass
cv2.setNumThreads(2)
with tempfile.TemporaryDirectory() as work:
    pdf = fitz.open()
    page = pdf.new_page(width=720, height=480)
    page.insert_text((45, 80), 'QUESTAO 01 - ESTUDO PARA CONCURSO', fontsize=24)
    page.insert_text((45, 130), 'A) Primeira alternativa. B) Segunda alternativa.', fontsize=20)
    path = Path(work) / 'native.pdf'
    pdf.save(path)
    with fitz.open(path) as saved:
        assert 'CONCURSO' in saved[0].get_text()
        pixmap = saved[0].get_pixmap(dpi=120, alpha=False)
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        lines, _ = engine(image)
        text = ' '.join(item[1] for item in (lines or []))
        assert 'CONCURSO' in text.upper(), text
    pdf.close()
print('CONCURSE_ANDROID_ENGINE_OK: API, AES-GCM, session, search backend, PDF text and OCR passed', flush=True)
""".trimIndent())
    }
}
