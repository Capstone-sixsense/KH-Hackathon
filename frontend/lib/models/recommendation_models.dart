class RecommendRequest {
  const RecommendRequest({
    required this.query,
    this.topN = 10,
  });

  final String query;
  final int topN;

  Map<String, dynamic> toJson() {
    return {
      'query': query,
      'top_n': topN,
    };
  }
}

class TrackRecommendation {
  const TrackRecommendation({
    required this.name,
    required this.artist,
    this.spotifyId,
    this.albumArtUrl,
    this.popularity,
    this.matchScore,
    this.tagRank,
    this.reverseScore,
    this.algo = '',
    this.label = '',
    this.reasonTags = const [],
  });

  final String name;
  final String artist;
  final String? spotifyId;
  final String? albumArtUrl;
  final int? popularity;
  final num? matchScore;
  final int? tagRank;
  final num? reverseScore;
  final String algo;
  final String label;
  final List<String> reasonTags;

  factory TrackRecommendation.fromJson(Map<String, dynamic> json) {
    return TrackRecommendation(
      name: json['name'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      spotifyId: json['spotify_id'] as String?,
      albumArtUrl: json['album_art_url'] as String?,
      popularity: (json['popularity'] as num?)?.toInt(),
      matchScore: json['match_score'] as num?,
      tagRank: (json['tag_rank'] as num?)?.toInt(),
      reverseScore: json['reverse_score'] as num?,
      algo: json['algo'] as String? ?? '',
      label: json['label'] as String? ?? '',
      reasonTags: (json['reason_tags'] as List<dynamic>? ?? const []).map((e) => e.toString()).toList(),
    );
  }
}

class RecommendResponse {
  const RecommendResponse({
    required this.trackName,
    required this.artist,
    required this.topN,
    required this.similar,
    required this.reverse,
    required this.opposite,
  });

  final String trackName;
  final String artist;
  final int topN;
  final List<TrackRecommendation> similar;
  final List<TrackRecommendation> reverse;
  final List<TrackRecommendation> opposite;

  factory RecommendResponse.fromJson(Map<String, dynamic> json) {
    final result = (json['result'] as Map<String, dynamic>? ?? const {});
    return RecommendResponse(
      trackName: json['track_name'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      topN: (json['top_n'] as num?)?.toInt() ?? 10,
      similar: (result['similar'] as List<dynamic>? ?? const [])
          .map((e) => TrackRecommendation.fromJson(e as Map<String, dynamic>))
          .toList(),
      reverse: (result['reverse'] as List<dynamic>? ?? const [])
          .map((e) => TrackRecommendation.fromJson(e as Map<String, dynamic>))
          .toList(),
      opposite: (result['opposite'] as List<dynamic>? ?? const [])
          .map((e) => TrackRecommendation.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
