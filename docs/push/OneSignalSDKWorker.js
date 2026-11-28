// OneSignal's push service worker, in its own folder (scope ./push/) so it
// never interferes with the site's own sw.js. Receives the match notifications.
importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js");
