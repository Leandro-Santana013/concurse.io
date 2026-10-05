# Python calls these methods through the Java bridge, so R8 cannot see them.
-keep class io.concurse.desktop.ProcessingService { public static *; }
# AndroidJUnitRunner calls this via the release app classpath. R8 cannot see
# test APK references when shrinking the production APK.
-keep class androidx.tracing.** { *; }
