plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// Release signing comes from the environment: GitHub Actions secrets in the release workflow,
// or variables the author exports locally. Without all four values and an existing keystore the
// release APK is built unsigned (app-release-unsigned.apk), so ordinary builds never need the key.
val releaseKeystore = System.getenv("MUSICDESK_KEYSTORE_FILE")?.takeIf { it.isNotBlank() }?.let { file(it) }
val releaseSigningReady = releaseKeystore?.isFile == true &&
    listOf("MUSICDESK_KEYSTORE_PASSWORD", "MUSICDESK_KEY_ALIAS", "MUSICDESK_KEY_PASSWORD")
        .all { !System.getenv(it).isNullOrBlank() }

android {
    namespace = "com.musicdesk.android"
    compileSdk = 36
    buildFeatures {
        buildConfig = true
    }

    defaultConfig {
        applicationId = "com.musicdesk.android"
        minSdk = 24
        targetSdk = 35
        versionCode = 3
        versionName = "0.3.0"
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        if (releaseSigningReady) {
            create("release") {
                storeFile = releaseKeystore
                storePassword = System.getenv("MUSICDESK_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("MUSICDESK_KEY_ALIAS")
                keyPassword = System.getenv("MUSICDESK_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        getByName("release") {
            if (releaseSigningReady) signingConfig = signingConfigs.getByName("release")
        }
    }
}

chaquopy {
    sourceSets {
        getByName("main") {
            srcDir(rootProject.projectDir.parentFile)
            include("musicdesk_core/**", "musicdesk_downloader.py")
        }
    }
    defaultConfig {
        version = "3.14"
        pip {
            install("yt-dlp==2026.08.19")
            install("mutagen==1.48.1")
            install("yt-dlp-ejs")
        }
    }
}

dependencies {
    implementation("com.arthenica:ffmpeg-kit-next:9.0.1")
    testImplementation("junit:junit:4.13.2")
}

