import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:khuthon/models/recommendation_models.dart';

class RecommendationApi {
  RecommendationApi({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<RecommendResponse> recommend(RecommendRequest request) async {
    final uri = Uri.parse('${_resolveBaseUrl()}/recommend');
    final response = await _client.post(
      uri,
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(request.toJson()),
    );

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('추천 API 호출 실패: ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return RecommendResponse.fromJson(decoded);
  }

  String _resolveBaseUrl() => RecommendationApi.resolveBaseUrl();

  static String resolveBaseUrl() {
    const fromDefine = String.fromEnvironment('API_BASE_URL', defaultValue: '');
    if (fromDefine.isNotEmpty) {
      final normalized = fromDefine.trim().toLowerCase();
      if (normalized.startsWith('backend:') || normalized.contains('://backend')) {
        return 'http://127.0.0.1:8000';
      }
      final parsed = Uri.tryParse(fromDefine);
      if (parsed != null) {
        final host = parsed.host;
        // docker-compose build arg로 주입된 backend 호스트는 브라우저에서 해석되지 않는다.
        if (host == 'backend' || host == '0.0.0.0' || host == 'localhost' || host == '::1') {
          return '${parsed.scheme.isEmpty ? 'http' : parsed.scheme}://127.0.0.1:8000';
        }
      }
      return fromDefine;
    }

    final base = Uri.base;
    final host = base.host;
    // macOS/Chrome 환경에서 localhost가 ::1(IPv6 loopback)로 해석되면
    // Docker 포트 포워딩과 충돌해 ClientException이 날 수 있어 IPv4를 강제한다.
    if (host == 'localhost' || host == '127.0.0.1' || host == '::1' || host == '[::1]') {
      return '${base.scheme}://127.0.0.1:8000';
    }
    return '${base.scheme}://$host:8000';
  }
}
