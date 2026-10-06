plugins {
    id("com.android.application")
}

android {
    namespace = "com.musicdesk.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.musicdesk.android"
        minSdk = 23
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    sourceSets.getByName("main").assets.srcDir(layout.buildDirectory.dir("generated/musicdeskAssets"))
}

val syncMusicDeskAssets by tasks.registering(Sync::class) {
    from(rootProject.projectDir.parentFile) {
        include("index.html", "default_song_img.png")
    }
    into(layout.buildDirectory.dir("generated/musicdeskAssets"))
}

tasks.named("preBuild").configure {
    dependsOn(syncMusicDeskAssets)
}
