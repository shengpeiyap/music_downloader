plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

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
        versionCode = 2
        versionName = "0.2.0"
        ndk {
            abiFilters += listOf("arm64-v8a")
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

