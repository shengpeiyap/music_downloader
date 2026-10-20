pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        maven { url = uri("$rootDir/ffmpeg-kit-maven") }
        mavenCentral()
    }
}

rootProject.name = "MusicDeskAndroid"
include(":app")
