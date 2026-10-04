// Applied by prepare-android-engine.mjs to the generated Tauri Android project.
val engineProperties = Properties().apply {
    file("../concurse-engine.properties").inputStream().use { load(it) }
}

android {
    testBuildType = "release"
    defaultConfig {
        ndk { abiFilters += listOf("arm64-v8a") }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "CONCURSE_SUPABASE_URL", engineProperties.getProperty("supabaseUrl"))
        buildConfigField("String", "CONCURSE_SUPABASE_PUBLISHABLE_KEY", engineProperties.getProperty("publishableKey"))
    }
    // The published mobile build is ARM64. Tauri also creates 32-bit flavors,
    // which cannot load the Python 3.12 processing runtime.
    productFlavors.configureEach {
        ndk { abiFilters.clear(); abiFilters += listOf("arm64-v8a") }
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        buildPython(engineProperties.getProperty("buildPython"))
        pip {
            options("--extra-index-url", "https://pypi.flet.dev")
            install("-r", file("../../../../engine/android/requirements.txt").absolutePath)
        }
        extractPackages("rapidocr_onnxruntime", "cv2", "pymupdf", "services.pdf_pipeline.fallbacks")
    }
    sourceSets.getByName("main") {
        setSrcDirs(listOf(file("../../../../.engine-build/android/source")))
    }
}

// Register after Chaquopy has attached the pip action, so adaptation executes
// after installation and is included in the task's output snapshot.
afterEvaluate {
tasks.matching { it.name.startsWith("install") && it.name.endsWith("PythonRequirements") }.configureEach {
    val adapter = file("../../../../engine/android/normalize_native_wheels.py")
    inputs.file(adapter)
    doLast {
        val variant = name.removePrefix("install").removeSuffix("PythonRequirements").replaceFirstChar { it.lowercase() }
        project.exec {
            commandLine(engineProperties.getProperty("buildPython"), adapter.absolutePath,
                layout.buildDirectory.dir("python/pip/$variant").get().asFile.absolutePath)
        }
    }
}
}
