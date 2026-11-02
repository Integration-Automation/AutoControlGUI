plugins {
    kotlin("jvm") version "2.0.21" apply false
    kotlin("android") version "2.0.21" apply false
    id("com.android.application") version "8.7.3" apply false
}

// Every resolved configuration is locked. Until a project's gradle.lockfile exists Gradle
// resolves as before; `--write-locks` writes them (see the android-helper workflow).
allprojects {
    dependencyLocking {
        lockAllConfigurations()
    }
}
