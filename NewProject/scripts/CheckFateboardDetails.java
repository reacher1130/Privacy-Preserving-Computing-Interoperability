// Compile/run inside the Board container against its installed JAR and lib/*.
// Account credentials remain in the container; output contains assertions only.
import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import org.fedai.fate.board.utils.RSAUtils;
import org.fedai.fate.board.utils.StandardRSAUtils;

import javax.websocket.ClientEndpointConfig;
import javax.websocket.ContainerProvider;
import javax.websocket.Endpoint;
import javax.websocket.EndpointConfig;
import javax.websocket.MessageHandler;
import javax.websocket.Session;
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.InputStream;
import java.net.CookieHandler;
import java.net.CookieManager;
import java.net.HttpCookie;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

public class CheckFateboardDetails {
    private static JSONObject request(String method, String path, JSONObject body) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL("http://127.0.0.1:8080" + path).openConnection();
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(20000);
        connection.setRequestMethod(method);
        if (body != null) {
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.getOutputStream().write(body.toJSONString().getBytes(StandardCharsets.UTF_8));
        }
        require(connection.getResponseCode() == 200, "Board HTTP request failed");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (InputStream stream = connection.getInputStream()) {
            byte[] buffer = new byte[4096];
            int length;
            while ((length = stream.read(buffer)) != -1) {
                require(bytes.size() + length <= 2 * 1024 * 1024, "Board response exceeds test limit");
                bytes.write(buffer, 0, length);
            }
        }
        return JSON.parseObject(new String(bytes.toByteArray(), StandardCharsets.UTF_8));
    }

    private static JSONObject call(String method, String path, JSONObject body) throws Exception {
        JSONObject reply = request(method, path, body);
        require(Integer.valueOf(0).equals(reply.getInteger("code")), "Board API returned an error: " + path);
        return reply;
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    public static void main(String[] args) throws Exception {
        require(args.length >= 3 && args.length <= 5, "Expected job ID, role, party ID, optional PSI rows and Guest party ID");
        final String job = args[0], role = args[1], party = args[2];
        final Integer expectedPsiRows = args.length >= 4 ? Integer.valueOf(args[3]) : null;
        final String guestParty = args.length == 5 ? args[4] : null;
        final int components = expectedPsiRows == null ? 3 : 2;
        final String summaryPath = "/job/query/" + job + "/" + role + "/" + party;
        if (expectedPsiRows != null) {
            require(request("GET", summaryPath, null).getIntValue("code") == 10015,
                    "Anonymous Board query was not denied");
        }
        CookieManager cookies = new CookieManager();
        CookieHandler.setDefault(cookies);
        Properties properties = new Properties();
        try (InputStream input = new FileInputStream("conf/application.properties")) { properties.load(input); }
        String password = properties.getProperty("server.board.login.password");
        if (Boolean.parseBoolean(properties.getProperty("server.board.encrypt.enable", "false"))) {
            password = StandardRSAUtils.decryptByPrivateKey(password, properties.getProperty("server.board.encrypt.private_key"));
        }
        String publicKey = call("POST", "/user/getKey", new JSONObject()).getString("data");
        JSONObject login = new JSONObject();
        login.put("username", properties.getProperty("server.board.login.username"));
        login.put("password", RSAUtils.encrypt(password, publicKey));
        require(Boolean.TRUE.equals(call("POST", "/user/login", login).getBoolean("data")), "Board login failed");

        JSONObject query = new JSONObject();
        query.put("job_id", job); query.put("role", role); query.put("party_id", party);
        JSONObject summary = call("GET", summaryPath, null).getJSONObject("data");
        require(summary != null && summary.getJSONObject("job") != null, "Board HTTP summary missing");
        JSONObject dag = call("POST", "/v1/pipeline/dag/dependencies", query).getJSONObject("data");
        require(dag != null && dag.getJSONArray("component_list").size() >= components, "Board HTTP DAG missing");
        JSONObject componentQuery = new JSONObject(query);
        if (expectedPsiRows == null) {
            componentQuery.put("component_name", "coordinated_lr_1");
            JSONObject component = JSON.parseObject(call("POST", "/v1/tracking/component/parameters", componentQuery).getString("data"));
            require(component.getJSONObject("parameters").getIntValue("epochs") == 2, "Board LR parameters missing");
        } else {
            componentQuery.put("component_name", "psi_0");
            JSONObject output = call("POST", "/v1/tracking/component/output/data", componentQuery).getJSONObject("data");
            require(output != null && output.getJSONArray("output_data") != null && output.getJSONArray("output_data").size() == 1
                    && expectedPsiRows.equals(output.getJSONArray("output_data").getJSONObject(0).getInteger("total")),
                    "Board PSI output row count differs from native result");
            if (guestParty != null) {
                require("host".equals(role), "The optional Guest party applies only to Host verification");
                JSONObject guest = request("GET", "/job/query/" + job + "/guest/" + guestParty, null);
                Object guestData = guest.get("data");
                require(!(guestData instanceof JSONObject) || ((JSONObject) guestData).getJSONObject("job") == null,
                        "Host Board returned a Guest job record");
            }
        }

        final CountDownLatch received = new CountDownLatch(1);
        final AtomicReference<JSONObject> message = new AtomicReference<>();
        ClientEndpointConfig config = ClientEndpointConfig.Builder.create().configurator(new ClientEndpointConfig.Configurator() {
            @Override public void beforeRequest(Map<String, List<String>> headers) {
                String cookie = cookies.getCookieStore().getCookies().stream().map(HttpCookie::toString).collect(Collectors.joining("; "));
                headers.put("Cookie", Collections.singletonList(cookie));
            }
        }).build();
        Endpoint endpoint = new Endpoint() {
            @Override public void onOpen(Session session, EndpointConfig configuration) {
                session.addMessageHandler(new MessageHandler.Whole<String>() {
                    @Override public void onMessage(String text) {
                        try { message.set(JSON.parseObject(text)); } catch (Exception ignored) { }
                        received.countDown();
                    }
                });
            }
            @Override public void onError(Session session, Throwable error) { received.countDown(); }
        };
        Session socket = ContainerProvider.getWebSocketContainer().connectToServer(endpoint, config,
                new URI("ws://127.0.0.1:8080/websocket/progress/" + job + "/" + role + "/" + party));
        require(received.await(25, TimeUnit.SECONDS), "Board detail WebSocket timed out");
        JSONObject payload = message.get();
        if (socket.isOpen()) socket.close();
        require(payload != null && payload.getJSONObject("summary_date") != null, "Board WebSocket summary missing");
        require(payload.getJSONObject("dependency_data").getJSONArray("component_list").size() >= components, "Board WebSocket DAG missing");
        require("success".equals(payload.getString("status")), "Board WebSocket job status differs from native result");
        JSONObject result = new JSONObject();
        result.put("pass", true); result.put("job_id", job); result.put("role", role); result.put("party_id", party);
        result.put("http_summary", true); result.put("http_dag_components", dag.getJSONArray("component_list").size());
        if (expectedPsiRows == null) result.put("component_parameters_epochs", 2);
        else {
            result.put("psi_output_rows", expectedPsiRows);
            result.put("anonymous_rejected", true);
            if (guestParty != null) result.put("guest_record_absent", true);
        }
        result.put("ws_summary", true);
        result.put("ws_dag_components", payload.getJSONObject("dependency_data").getJSONArray("component_list").size());
        result.put("ws_status", payload.getString("status"));
        System.out.println("BOARD_DETAIL_CHECK=" + result.toJSONString());
    }
}
