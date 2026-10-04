# Python calls these methods through the Java bridge, so R8 cannot see them.
-keep class io.concurse.desktop.ProcessingService { public static *; }
