package np.gov.helpdesk

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.android.Android
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class QueryRequest(
    val question: String,
    val top_k_tacit: Int = 3,
    val top_k_gov: Int = 3,
    val max_new_tokens: Int = 600,
)

@Serializable
data class CitationOut(
    val url: String,
    val rank: Int,
    val snippet: String,
    val is_tacit: Boolean = false,
)

@Serializable
data class SourceOut(
    val rank: Int,
    val is_tacit: Boolean,
    val label: String,
    val url: String? = null,
    val snippet: String,
    val confidence: String? = null,
    val interviewee_role: String? = null,
)

@Serializable
data class QueryResponse(
    val answer: String,
    val citations: List<CitationOut>,
    val sources: List<SourceOut>,
    val did_refuse: Boolean,
    val retrieved_tacit: Int,
    val retrieved_gov: Int,
    val latency_ms: Map<String, Int>,
    val detected_lang: String,
)

@Serializable
data class HealthOut(
    val status: String,
    val model_id: String,
    val adapter: String? = null,
    val model_loaded: Boolean,
    val db_loaded: Boolean,
    val startup_at: String,
)

/**
 * Stateless wrapper around the helpdesk RAG endpoint. Each call rebuilds the
 * client from current Prefs so changing the server URL in Settings takes
 * effect immediately.
 */
class RagClient(private val prefs: Prefs) {

    private fun client(): HttpClient = HttpClient(Android) {
        install(ContentNegotiation) {
            json(Json {
                ignoreUnknownKeys = true
                isLenient = true
            })
        }
        install(HttpTimeout) {
            connectTimeoutMillis = 5_000
            requestTimeoutMillis = 120_000  // generation can be slow
            socketTimeoutMillis = 120_000
        }
    }

    suspend fun query(question: String): Result<QueryResponse> = runCatching {
        client().use { c ->
            val resp = c.post("${prefs.serverUrl}/query") {
                contentType(ContentType.Application.Json)
                if (prefs.bearerToken.isNotEmpty()) bearerAuth(prefs.bearerToken)
                setBody(QueryRequest(question))
            }
            resp.body<QueryResponse>()
        }
    }

    suspend fun health(): Result<HealthOut> = runCatching {
        client().use { c ->
            c.get("${prefs.serverUrl}/health").body<HealthOut>()
        }
    }
}
