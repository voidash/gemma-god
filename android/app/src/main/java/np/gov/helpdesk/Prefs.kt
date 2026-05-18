package np.gov.helpdesk

import android.content.Context
import android.content.SharedPreferences

/**
 * Server URL + bearer token persistence.
 *
 * v0.1 uses SharedPreferences for simplicity. Upgrade to DataStore later
 * if we add reactive state-flow needs.
 */
class Prefs(context: Context) {
    private val sp: SharedPreferences =
        context.getSharedPreferences("gemma_god_prefs", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = sp.getString(KEY_URL, DEFAULT_URL) ?: DEFAULT_URL
        set(v) = sp.edit().putString(KEY_URL, v.trim().trimEnd('/')).apply()

    var bearerToken: String
        get() = sp.getString(KEY_TOKEN, "") ?: ""
        set(v) = sp.edit().putString(KEY_TOKEN, v.trim()).apply()

    companion object {
        private const val KEY_URL = "server_url"
        private const val KEY_TOKEN = "bearer_token"
        // Default points at the local k2 reachable via Tailscale-100-net IP.
        // User changes this in Settings to whatever the demo server is.
        private const val DEFAULT_URL = "http://100.64.0.1:8000"
    }
}
