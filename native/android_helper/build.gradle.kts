plugins {
    kotlin("jvm") version "2.0.21" apply false
    kotlin("android") version "2.0.21" apply false
    id("com.android.application") version "8.7.3" apply false
}

// Every resolved configuration is locked by the gradle.lockfile next to each project.
// After changing a dependency, refresh them with
//   gradle -p native/android_helper dependencies :core:dependencies :app:dependencies --write-locks
allprojects {
    dependencyLocking {
        lockAllConfigurations()
    }
}
