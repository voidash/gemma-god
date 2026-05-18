package np.gov.helpdesk

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import kotlinx.coroutines.launch

/** Single-activity entry point. Two screens: Chat + Settings. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = Prefs(applicationContext)
        setContent {
            MaterialTheme(colorScheme = lightColorScheme()) {
                val nav = rememberNavController()
                NavHost(navController = nav, startDestination = "chat") {
                    composable("chat") {
                        ChatScreen(
                            prefs = prefs,
                            onOpenSettings = { nav.navigate("settings") },
                        )
                    }
                    composable("settings") {
                        SettingsScreen(
                            prefs = prefs,
                            onBack = { nav.popBackStack() },
                        )
                    }
                }
            }
        }
    }
}

// ---- Chat ------------------------------------------------------------------

data class ChatMessage(
    val text: String,
    val isUser: Boolean,
    val response: QueryResponse? = null,
    val error: String? = null,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(prefs: Prefs, onOpenSettings: () -> Unit) {
    val messages = remember { mutableStateListOf<ChatMessage>() }
    var input by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val client = remember(prefs.serverUrl, prefs.bearerToken) { RagClient(prefs) }
    val listState = rememberLazyListState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Nepal Gov Helpdesk") },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.padding(padding).fillMaxSize()) {
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).padding(horizontal = 12.dp),
                contentPadding = PaddingValues(vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (messages.isEmpty() && !loading) {
                    item { EmptyHint() }
                }
                items(messages) { m -> MessageBubble(m) }
                if (loading) {
                    item { ThinkingIndicator() }
                }
            }
            InputBar(
                input = input,
                onInputChange = { input = it },
                enabled = !loading,
                onSend = {
                    val q = input.trim()
                    if (q.isEmpty()) return@InputBar
                    messages.add(ChatMessage(q, isUser = true))
                    input = ""
                    loading = true
                    scope.launch {
                        client.query(q)
                            .onSuccess { resp ->
                                messages.add(ChatMessage(resp.answer, isUser = false, response = resp))
                            }
                            .onFailure { e ->
                                messages.add(ChatMessage("", isUser = false, error = e.message ?: "Network error"))
                            }
                        loading = false
                        listState.animateScrollToItem(messages.size)
                    }
                },
            )
        }
    }
}

@Composable
fun EmptyHint() {
    Card(modifier = Modifier.fillMaxWidth().padding(8.dp)) {
        Text(
            text = "Hi! Ask anything about Nepal-government services. " +
                "I cite my sources, and refuse if I can't find an authoritative one.",
            modifier = Modifier.padding(16.dp),
        )
    }
}

@Composable
fun ThinkingIndicator() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(strokeWidth = 2.dp, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(8.dp))
        Text("Thinking…")
    }
}

@Composable
fun MessageBubble(m: ChatMessage) {
    val context = LocalContext.current
    val align = if (m.isUser) Alignment.End else Alignment.Start
    val bg = if (m.isUser) MaterialTheme.colorScheme.primaryContainer
        else MaterialTheme.colorScheme.surfaceVariant
    Column(modifier = Modifier.fillMaxWidth(), horizontalAlignment = align) {
        Surface(
            color = bg,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.widthIn(max = 320.dp),
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                if (m.error != null) {
                    Text("Error: ${m.error}", color = MaterialTheme.colorScheme.error)
                } else {
                    Text(m.text)
                }
                if (m.response != null) {
                    val r = m.response
                    Spacer(Modifier.height(8.dp))
                    if (r.did_refuse) {
                        FilledTonalButton(
                            onClick = {
                                val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:1111"))
                                context.startActivity(intent)
                            },
                        ) {
                            Icon(Icons.Default.Call, contentDescription = null)
                            Spacer(Modifier.width(6.dp))
                            Text("Call Hello Sarkar 1111")
                        }
                        Spacer(Modifier.height(8.dp))
                    }
                    if (r.sources.isNotEmpty()) {
                        Text(
                            "Sources (${r.sources.size}):",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                        )
                        Spacer(Modifier.height(4.dp))
                        r.sources.forEach { s -> SourceCard(s) }
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "${r.detected_lang} · ${r.latency_ms["total"] ?: 0} ms · " +
                            "${r.retrieved_tacit} tacit + ${r.retrieved_gov} gov",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
fun SourceCard(s: SourceOut) {
    val context = LocalContext.current
    val labelColor = if (s.is_tacit) Color(0xFF1B5E20) else Color(0xFF1565C0)
    Surface(
        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 1.dp,
        onClick = {
            val u = s.url ?: return@Surface
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(u))
            context.startActivity(intent)
        },
    ) {
        Column(modifier = Modifier.padding(8.dp)) {
            Row {
                Text(
                    text = s.label,
                    color = labelColor,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelSmall,
                )
                if (s.confidence != null) {
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = "·  ${s.confidence}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (s.interviewee_role != null) {
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = "·  ${s.interviewee_role}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Text(s.snippet, style = MaterialTheme.typography.bodySmall, maxLines = 4, overflow = TextOverflow.Ellipsis)
            if (s.url != null) {
                Text(
                    s.url,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
fun InputBar(input: String, onInputChange: (String) -> Unit, enabled: Boolean, onSend: () -> Unit) {
    Surface(tonalElevation = 2.dp) {
        Row(
            modifier = Modifier.padding(8.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = input,
                onValueChange = onInputChange,
                modifier = Modifier.weight(1f),
                enabled = enabled,
                placeholder = { Text("Ask in Nepali, Roman-Nepali, or English…") },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                singleLine = false,
                maxLines = 4,
            )
            Spacer(Modifier.width(8.dp))
            FilledIconButton(onClick = onSend, enabled = enabled && input.isNotBlank()) {
                Icon(Icons.Default.Send, contentDescription = "Send")
            }
        }
    }
}

// ---- Settings --------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(prefs: Prefs, onBack: () -> Unit) {
    var url by remember { mutableStateOf(prefs.serverUrl) }
    var token by remember { mutableStateOf(prefs.bearerToken) }
    var status by remember { mutableStateOf<String?>(null) }
    var testing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Scaffold(
        topBar = { TopAppBar(title = { Text("Settings") }, navigationIcon = {
            TextButton(onClick = onBack) { Text("Back") }
        }) },
    ) { padding ->
        Column(
            modifier = Modifier.padding(padding).padding(16.dp).fillMaxWidth().verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                "Server URL",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
            )
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("https://k2.your-tailnet.ts.net") },
                singleLine = true,
            )
            Text(
                "Bearer token (optional — leave blank if server doesn't require it)",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("(no token)") },
                singleLine = true,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = {
                        prefs.serverUrl = url
                        prefs.bearerToken = token
                        status = "Saved."
                    },
                ) {
                    Text("Save")
                }
                OutlinedButton(
                    onClick = {
                        prefs.serverUrl = url
                        prefs.bearerToken = token
                        testing = true
                        status = "Testing…"
                        scope.launch {
                            val client = RagClient(prefs)
                            client.health()
                                .onSuccess { h ->
                                    status = "OK · model=${h.model_id} · adapter=${h.adapter ?: "(base)"}" +
                                        " · model_loaded=${h.model_loaded} · db_loaded=${h.db_loaded}"
                                }
                                .onFailure { e ->
                                    status = "Failed: ${e.message}"
                                }
                            testing = false
                        }
                    },
                    enabled = !testing,
                ) {
                    Text(if (testing) "Testing…" else "Test connection")
                }
            }
            if (status != null) {
                Text(status!!, fontSize = 14.sp)
            }
        }
    }
}
