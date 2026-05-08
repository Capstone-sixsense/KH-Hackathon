import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:khuthon/models/recommendation_models.dart';
import 'package:khuthon/widgets/turntable_tonearm.dart';

enum _TrackViewMode { gallery, list }

class ResultScreen extends StatefulWidget {
  const ResultScreen({
    super.key,
    required this.keyword,
    required this.response,
  });

  final String keyword;
  final RecommendResponse response;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _introController;
  late final Animation<double> _mainCardOpacity;
  late final Animation<double> _mainCardScale;
  late final Animation<double> _edgeProgress;

  @override
  void initState() {
    super.initState();
    _introController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2100),
    );
    _mainCardOpacity = CurvedAnimation(
      parent: _introController,
      curve: const Interval(0.0, 0.14, curve: Curves.easeOutCubic),
    );
    _mainCardScale = Tween<double>(begin: 0.94, end: 1.0).animate(
      CurvedAnimation(
        parent: _introController,
        curve: const Interval(0.0, 0.16, curve: Curves.easeOutCubic),
      ),
    );
    _edgeProgress = CurvedAnimation(
      parent: _introController,
      curve: const Interval(0.08, 0.34, curve: Curves.easeInOutCubic),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Future<void>.delayed(const Duration(milliseconds: 180), () {
        if (!mounted) {
          return;
        }
        _introController.forward(from: 0);
      });
    });
  }

  @override
  void dispose() {
    _introController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final allTracks = <TrackRecommendation>[
      ...widget.response.similar,
      ...widget.response.reverse,
      ...widget.response.opposite,
      ...widget.response.hidden,
    ];
    final mainTrack = _buildMainTrack(allTracks);
    final groups = [
      _NodeData(
        label: '밀려난 유사곡들',
        description: '상위 추천 밖의 저노출 유사곡',
        angle: -2.35,
        ring: 0.78,
        sizeScale: 1.26,
        color: const Color(0xFFD38FB4),
        tracks: widget.response.reverse,
      ),
      _NodeData(
        label: '취향이 겹치는 곡들',
        description: '청취 패턴이 가까운 곡',
        angle: -0.58,
        ring: 0.64,
        sizeScale: 0.94,
        color: const Color(0xFF7CBFB3),
        tracks: widget.response.similar,
      ),
      _NodeData(
        label: '반대 무드의 곡들',
        description: '감정선이 다른 곡',
        angle: 0.62,
        ring: 0.82,
        sizeScale: 0.94,
        color: const Color(0xFF8A95A6),
        tracks: widget.response.opposite,
      ),
      _NodeData(
        label: '닮은 아티스트 곡들',
        description: '다른 아티스트 추천',
        angle: 2.22,
        ring: 0.72,
        sizeScale: 1.13,
        color: const Color(0xFFD4A157),
        tracks: widget.response.hidden,
      ),
    ];

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Stack(
                alignment: Alignment.center,
                children: [
                  Align(
                    alignment: Alignment.centerLeft,
                    child: IconButton(
                      tooltip: '뒤로',
                      onPressed: () => Navigator.of(context).pop(),
                      icon: const Icon(Icons.arrow_back_ios_new_rounded),
                    ),
                  ),
                  _SearchTagBar(tags: _buildSearchTags(widget.keyword)),
                ],
              ),
              const SizedBox(height: 18),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final shortest = math.min(
                      constraints.maxWidth,
                      constraints.maxHeight,
                    );
                    final availableRadius =
                        math.min(constraints.maxWidth, constraints.maxHeight) *
                        0.48;
                    final recordRadius = math.min(
                      (shortest * 0.47).clamp(190.0, 420.0).toDouble(),
                      availableRadius,
                    );
                    final mainCardSize = (recordRadius * 0.726)
                        .clamp(202.0, 315.0)
                        .toDouble();
                    final baseNodeSize = (recordRadius * 0.418)
                        .clamp(134.0, 178.0)
                        .toDouble();
                    final center = Offset(
                      constraints.maxWidth * 0.5,
                      constraints.maxHeight * 0.51,
                    );
                    return AnimatedBuilder(
                      animation: _introController,
                      builder: (context, _) {
                        return Stack(
                          clipBehavior: Clip.none,
                          children: [
                            CustomPaint(
                              size: Size(
                                constraints.maxWidth,
                                constraints.maxHeight,
                              ),
                              painter: _VinylMapPainter(
                                center: center,
                                radius: recordRadius,
                                nodes: groups,
                                progress: _edgeProgress.value,
                                ripple: _introController.value,
                              ),
                            ),
                            Positioned(
                              left: center.dx + (recordRadius * 0.31),
                              top: center.dy - (recordRadius * 0.74),
                              child: IgnorePointer(
                                child: TurntableTonearm(
                                  size: recordRadius * 0.62,
                                  accent: const Color(0xFFF472B6),
                                  opacity: 0.94,
                                  rotation: -0.06,
                                ),
                              ),
                            ),
                            Positioned(
                              left: center.dx - (mainCardSize / 2),
                              top: center.dy - (mainCardSize / 2),
                              child: FadeTransition(
                                opacity: _mainCardOpacity,
                                child: ScaleTransition(
                                  scale: _mainCardScale,
                                  child: _MainTrackCard(
                                    mainTrack: mainTrack,
                                    size: mainCardSize,
                                  ),
                                ),
                              ),
                            ),
                            ...groups.asMap().entries.map((entry) {
                              final node = entry.value;
                              final nodeSize = (baseNodeSize * node.sizeScale)
                                  .clamp(126.0, 224.0)
                                  .toDouble();
                              final nodeProgress = _nodeProgress(entry.key);
                              final nodeTranslateY = (1 - nodeProgress) * 14;
                              final nodeOffset = node.position(
                                center,
                                recordRadius,
                              );
                              return Positioned(
                                left: nodeOffset.dx - (nodeSize / 2),
                                top:
                                    nodeOffset.dy -
                                    (nodeSize / 2) +
                                    nodeTranslateY,
                                child: Opacity(
                                  opacity: nodeProgress,
                                  child: _GroupNode(
                                    node: node,
                                    size: nodeSize,
                                    enabled: node.tracks.isNotEmpty,
                                    onTap: () =>
                                        _openGroupTracks(context, node),
                                  ),
                                ),
                              );
                            }),
                          ],
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  double _nodeProgress(int index) {
    const baseStart = 0.56;
    const step = 0.045;
    const span = 0.16;
    final start = baseStart + (index * step);
    final end = (start + span).clamp(0.0, 1.0);
    final t = ((_introController.value - start) / (end - start))
        .clamp(0.0, 1.0)
        .toDouble();
    return Curves.easeOutCubic.transform(t);
  }

  List<String> _buildSearchTags(String keyword) {
    final normalized = keyword.trim();
    if (normalized.isEmpty) {
      return const [];
    }
    final commaTokens = normalized
        .split(',')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    if (commaTokens.length > 1) {
      return commaTokens;
    }
    final dashTokens = normalized
        .split('-')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    if (dashTokens.length > 1) {
      return dashTokens;
    }
    final spaceTokens = normalized
        .split(RegExp(r'\s+'))
        .where((e) => e.isNotEmpty)
        .toList();
    return spaceTokens;
  }

  _MainTrackData _buildMainTrack(List<TrackRecommendation> allTracks) {
    final baseName = widget.response.trackName.trim();
    final baseArtist = widget.response.artist.trim();

    String? albumArtUrl = widget.response.albumArtUrl;
    for (final track in allTracks) {
      final sameTitle =
          track.name.trim().toLowerCase() == baseName.toLowerCase();
      final sameArtist =
          track.artist.trim().toLowerCase() == baseArtist.toLowerCase();
      if ((albumArtUrl ?? '').isEmpty && sameTitle && sameArtist) {
        albumArtUrl = track.albumArtUrl;
        break;
      }
    }

    return _MainTrackData(
      title: baseName.isEmpty ? 'No Result' : baseName,
      artist: baseArtist.isEmpty ? '아티스트 정보 없음' : baseArtist,
      albumArtUrl: albumArtUrl,
      hasResult: baseName.isNotEmpty && baseArtist.isNotEmpty,
    );
  }

  Future<void> _openGroupTracks(BuildContext context, _NodeData node) async {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _GroupTracksScreen(
          title: node.label,
          subtitle: node.description,
          color: node.color,
          tracks: node.tracks,
          initialMode: _TrackViewMode.gallery,
        ),
      ),
    );
  }
}

class _MainTrackCard extends StatelessWidget {
  const _MainTrackCard({required this.mainTrack, required this.size});

  final _MainTrackData mainTrack;
  final double size;

  @override
  Widget build(BuildContext context) {
    final albumSize = (size * 0.31).clamp(58.0, 90.0).toDouble();
    final titleFontSize = (size * 0.078).clamp(15.5, 22.0).toDouble();
    final artistFontSize = (size * 0.055).clamp(11.5, 15.0).toDouble();
    return Container(
      width: size,
      height: size,
      padding: EdgeInsets.all(size * 0.09),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: const RadialGradient(
          colors: [Color(0xFFF3E8D5), Color(0xFFD6B986), Color(0xFF7A5E37)],
          stops: [0.0, 0.64, 1.0],
        ),
        border: Border.all(
          color: const Color(0xFFF7E9C9).withValues(alpha: 0.75),
          width: 2,
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x66000000),
            blurRadius: 28,
            offset: Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text(
            'Side-B Seed',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: Color(0xFF3B2B19),
              fontSize: 11,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          if ((mainTrack.albumArtUrl ?? '').isNotEmpty)
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Image.network(
                mainTrack.albumArtUrl!,
                width: albumSize,
                height: albumSize,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) =>
                    _fallbackArt(albumSize),
              ),
            )
          else
            _fallbackArt(albumSize),
          SizedBox(height: size * 0.045),
          Text(
            mainTrack.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Color(0xFF1F160E),
              height: 1.05,
              fontWeight: FontWeight.w900,
            ).copyWith(fontSize: titleFontSize),
          ),
          SizedBox(height: size * 0.022),
          Text(
            mainTrack.hasResult ? mainTrack.artist : '추천 결과를 찾지 못했어요',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Color(0xFF5A4226),
              fontWeight: FontWeight.w700,
            ).copyWith(fontSize: artistFontSize),
          ),
        ],
      ),
    );
  }

  Widget _fallbackArt(double albumSize) {
    return Container(
      width: albumSize,
      height: albumSize,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        gradient: const LinearGradient(
          colors: [Color(0xFF111827), Color(0xFF4B5563)],
        ),
      ),
      alignment: Alignment.center,
      child: Icon(
        Icons.music_note_rounded,
        size: albumSize * 0.48,
        color: Colors.white,
      ),
    );
  }
}

class _MainTrackData {
  const _MainTrackData({
    required this.title,
    required this.artist,
    required this.albumArtUrl,
    required this.hasResult,
  });

  final String title;
  final String artist;
  final String? albumArtUrl;
  final bool hasResult;
}

class _SearchTagBar extends StatelessWidget {
  const _SearchTagBar({required this.tags});

  final List<String> tags;

  @override
  Widget build(BuildContext context) {
    final visibleTags = tags.take(6).toList();
    final hasOverflow = tags.length > 6;
    final barTags = [...visibleTags, if (hasOverflow) '...'];
    const pastelColors = [
      Color(0xFFF6E8E9),
      Color(0xFFEAF4E2),
      Color(0xFFE7F3FC),
      Color(0xFFF0E8FB),
      Color(0xFFFFF0DC),
      Color(0xFFEAF7F1),
      Color(0xFFF1F5F9),
    ];

    return Wrap(
      spacing: 8,
      runSpacing: 8,
      alignment: WrapAlignment.center,
      children: List.generate(barTags.length, (index) {
        final tag = barTags[index];
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: pastelColors[index % pastelColors.length].withValues(
              alpha: 0.62,
            ),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            tag,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: Color(0xFF1F2937),
            ),
          ),
        );
      }),
    );
  }
}

class _GroupNode extends StatefulWidget {
  const _GroupNode({
    required this.node,
    required this.size,
    required this.enabled,
    required this.onTap,
  });

  final _NodeData node;
  final double size;
  final bool enabled;
  final VoidCallback onTap;

  @override
  State<_GroupNode> createState() => _GroupNodeState();
}

class _GroupNodeState extends State<_GroupNode> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final galleryTracks = widget.node.tracks.take(4).toList();
    final thumbSize = (widget.size * 0.3).clamp(40.0, 52.0).toDouble();
    final shellSize = widget.size * 0.69;
    final badgePadding = EdgeInsets.symmetric(
      horizontal: widget.size * 0.052,
      vertical: widget.size * 0.025,
    );
    final canTap = widget.enabled;
    return MouseRegion(
      onEnter: (_) {
        if (!canTap) {
          return;
        }
        setState(() => _hovered = true);
      },
      onExit: (_) => setState(() => _hovered = false),
      cursor: canTap
          ? SystemMouseCursors.click
          : SystemMouseCursors.basic,
      child: GestureDetector(
        onTap: canTap ? widget.onTap : null,
        child: AnimatedScale(
          scale: canTap && _hovered ? 1.06 : 1.0,
          duration: const Duration(milliseconds: 170),
          curve: Curves.easeOut,
          child: AnimatedOpacity(
            duration: const Duration(milliseconds: 200),
            opacity: canTap ? 1 : 0.5,
            child: SizedBox(
            width: widget.size,
            height: widget.size,
            child: Stack(
              alignment: Alignment.center,
              children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 170),
                  width: shellSize,
                  height: shellSize,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: const Color(0xFF15151D).withValues(alpha: 0.92),
                    border: Border.all(
                      color: widget.node.color.withValues(
                        alpha: canTap && _hovered ? 0.95 : 0.7,
                      ),
                      width: 1.4,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: widget.node.color.withValues(
                          alpha: canTap && _hovered ? 0.32 : 0.18,
                        ),
                        blurRadius: canTap && _hovered ? 22 : 16,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                ),
                Positioned(
                  left: widget.size * 0.16,
                  top: widget.size * 0.14,
                  child: _AlbumThumb(
                    track: galleryTracks.isNotEmpty ? galleryTracks[0] : null,
                    color: widget.node.color,
                    size: thumbSize,
                  ),
                ),
                Positioned(
                  right: widget.size * 0.16,
                  top: widget.size * 0.14,
                  child: _AlbumThumb(
                    track: galleryTracks.length > 1 ? galleryTracks[1] : null,
                    color: widget.node.color,
                    size: thumbSize,
                  ),
                ),
                Positioned(
                  left: widget.size * 0.28,
                  top: widget.size * 0.36,
                  child: _AlbumThumb(
                    track: galleryTracks.length > 2 ? galleryTracks[2] : null,
                    color: widget.node.color,
                    size: thumbSize,
                  ),
                ),
                Positioned(
                  right: widget.size * 0.28,
                  top: widget.size * 0.36,
                  child: _AlbumThumb(
                    track: galleryTracks.length > 3 ? galleryTracks[3] : null,
                    color: widget.node.color,
                    size: thumbSize,
                  ),
                ),
                Positioned(
                  right: widget.size * 0.12,
                  top: widget.size * 0.43,
                  child: Container(
                    padding: badgePadding,
                    decoration: BoxDecoration(
                      color: widget.node.color,
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: Colors.black.withValues(alpha: 0.25),
                      ),
                    ),
                    child: Text(
                      '${widget.node.tracks.length}',
                      style: TextStyle(
                        color: Color(0xFF101016),
                        fontSize: (widget.size * 0.07)
                            .clamp(11.0, 12.0)
                            .toDouble(),
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ),
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: widget.size * 0.035,
                  child: Column(
                    children: [
                      Text(
                        widget.node.label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: (widget.size * 0.085)
                              .clamp(12.0, 14.0)
                              .toDouble(),
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        widget.node.description,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: (widget.size * 0.07)
                              .clamp(10.0, 11.5)
                              .toDouble(),
                          color: Color(0xFFA1A1AA),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          ),
        ),
      ),
    );
  }
}

class _VinylMapPainter extends CustomPainter {
  _VinylMapPainter({
    required this.center,
    required this.radius,
    required this.nodes,
    required this.progress,
    required this.ripple,
  });

  final Offset center;
  final double radius;
  final List<_NodeData> nodes;
  final double progress;
  final double ripple;

  @override
  void paint(Canvas canvas, Size size) {
    final shadowPaint = Paint()..color = Colors.black.withValues(alpha: 0.34);
    canvas.drawCircle(center.translate(0, 18), radius * 1.01, shadowPaint);

    final recordPaint = Paint()
      ..shader = const RadialGradient(
        colors: [Color(0xFF30303A), Color(0xFF111118), Color(0xFF050507)],
        stops: [0.0, 0.46, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, radius, recordPaint);

    final rimPaint = Paint()
      ..color = const Color(0xFFE5E7EB).withValues(alpha: 0.12)
      ..strokeWidth = 1.2
      ..style = PaintingStyle.stroke;
    canvas.drawCircle(center, radius, rimPaint);

    for (var i = 0; i < 14; i++) {
      final grooveRadius = radius * (0.18 + (i * 0.055));
      final groovePaint = Paint()
        ..color = Colors.white.withValues(alpha: i.isEven ? 0.055 : 0.028)
        ..strokeWidth = i.isEven ? 1.1 : 0.7
        ..style = PaintingStyle.stroke;
      canvas.drawCircle(center, grooveRadius, groovePaint);
    }

    for (var i = 0; i < 3; i++) {
      final t = (ripple - (i * 0.12)).clamp(0.0, 1.0).toDouble();
      if (t <= 0) {
        continue;
      }
      final ripplePaint = Paint()
        ..color = const Color(0xFF7CBFB3).withValues(alpha: (1 - t) * 0.18)
        ..strokeWidth = 1.6
        ..style = PaintingStyle.stroke;
      canvas.drawCircle(center, radius * (0.24 + (0.72 * t)), ripplePaint);
    }

    final clampedProgress = progress.clamp(0.0, 1.0).toDouble();
    if (clampedProgress <= 0.001) {
      return;
    }

    for (final node in nodes) {
      final ringRadius = radius * node.ring;
      final arcRect = Rect.fromCircle(center: center, radius: ringRadius);
      final sweep = 0.62 * clampedProgress;
      final arcPaint = Paint()
        ..color = node.color.withValues(alpha: 0.42)
        ..strokeWidth =
            (1.6 + (node.tracks.length.clamp(0, 4).toDouble() * 0.35)) *
            node.sizeScale
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round;
      canvas.drawArc(arcRect, node.angle - (sweep / 2), sweep, false, arcPaint);

      final nodePosition = node.position(center, radius);
      final dotPaint = Paint()..color = node.color.withValues(alpha: 0.88);
      canvas.drawCircle(nodePosition, 4.2 * node.sizeScale, dotPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _VinylMapPainter oldDelegate) {
    return oldDelegate.center != center ||
        oldDelegate.radius != radius ||
        oldDelegate.nodes != nodes ||
        oldDelegate.progress != progress ||
        oldDelegate.ripple != ripple;
  }
}

class _NodeData {
  const _NodeData({
    required this.label,
    required this.description,
    required this.angle,
    required this.ring,
    required this.sizeScale,
    required this.color,
    required this.tracks,
  });

  final String label;
  final String description;
  final double angle;
  final double ring;
  final double sizeScale;
  final Color color;
  final List<TrackRecommendation> tracks;

  Offset position(Offset center, double radius) {
    return Offset(
      center.dx + (math.cos(angle) * radius * ring),
      center.dy + (math.sin(angle) * radius * ring),
    );
  }
}

class _AlbumThumb extends StatelessWidget {
  const _AlbumThumb({
    required this.track,
    required this.color,
    required this.size,
  });

  final TrackRecommendation? track;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    final url = track?.albumArtUrl ?? '';
    return ClipRRect(
      borderRadius: BorderRadius.circular(size / 2),
      child: Container(
        width: size,
        height: size,
        color: const Color(0xFF1D1D27),
        child: url.isNotEmpty
            ? Image.network(
                url,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) => _fallback(),
              )
            : _fallback(),
      ),
    );
  }

  Widget _fallback() {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [color.withValues(alpha: 0.45), const Color(0xFF111827)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: const Center(
        child: Icon(Icons.music_note_rounded, size: 14, color: Colors.white70),
      ),
    );
  }
}

class _GroupTracksScreen extends StatefulWidget {
  const _GroupTracksScreen({
    required this.title,
    required this.subtitle,
    required this.color,
    required this.tracks,
    required this.initialMode,
  });

  final String title;
  final String subtitle;
  final Color color;
  final List<TrackRecommendation> tracks;
  final _TrackViewMode initialMode;

  @override
  State<_GroupTracksScreen> createState() => _GroupTracksScreenState();
}

class _GroupTracksScreenState extends State<_GroupTracksScreen> {
  late _TrackViewMode _mode;

  @override
  void initState() {
    super.initState();
    _mode = widget.initialMode;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 12, 16, 14),
              child: Row(
                children: [
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.arrow_back_ios_new_rounded),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.title,
                          style: const TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '총 ${widget.tracks.length}곡',
                          style: TextStyle(
                            color: widget.color,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Center(
              child: Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A25),
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.12),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _ViewModeToggleChip(
                      icon: Icons.grid_view_rounded,
                      tooltip: '갤러리',
                      selected: _mode == _TrackViewMode.gallery,
                      color: widget.color,
                      onTap: () =>
                          setState(() => _mode = _TrackViewMode.gallery),
                    ),
                    const SizedBox(width: 6),
                    _ViewModeToggleChip(
                      icon: Icons.format_list_bulleted_rounded,
                      tooltip: '리스트',
                      selected: _mode == _TrackViewMode.list,
                      color: widget.color,
                      onTap: () => setState(() => _mode = _TrackViewMode.list),
                    ),
                  ],
                ),
              ),
            ),
            Expanded(
              child: widget.tracks.isEmpty
                  ? const Center(
                      child: Text(
                        '표시할 추천 곡이 없습니다.',
                        style: TextStyle(color: Color(0xFFA1A1AA)),
                      ),
                    )
                  : _mode == _TrackViewMode.gallery
                  ? GridView.builder(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                      gridDelegate:
                          const SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: 6,
                            mainAxisSpacing: 10,
                            crossAxisSpacing: 10,
                            childAspectRatio: 0.85,
                          ),
                      itemCount: widget.tracks.length,
                      itemBuilder: (context, index) {
                        final track = widget.tracks[index];
                        return _TrackGalleryCard(
                          track: track,
                          color: widget.color,
                        );
                      },
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                      itemCount: widget.tracks.length,
                      separatorBuilder: (context, index) =>
                          const SizedBox(height: 8),
                      itemBuilder: (context, index) {
                        final track = widget.tracks[index];
                        return _TrackListTile(
                          track: track,
                          color: widget.color,
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TrackGalleryCard extends StatelessWidget {
  const _TrackGalleryCard({required this.track, required this.color});

  final TrackRecommendation track;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF171721),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      padding: const EdgeInsets.all(6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 1,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: _TrackArt(url: track.albumArtUrl, color: color),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            track.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 2),
          Text(
            track.artist,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 10, color: Color(0xFFA1A1AA)),
          ),
        ],
      ),
    );
  }
}

class _ViewModeToggleChip extends StatelessWidget {
  const _ViewModeToggleChip({
    required this.icon,
    required this.tooltip,
    required this.selected,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final String tooltip;
  final bool selected;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            color: selected
                ? color.withValues(alpha: 0.22)
                : Colors.transparent,
            border: Border.all(
              color: selected
                  ? color.withValues(alpha: 0.72)
                  : Colors.white.withValues(alpha: 0.1),
            ),
          ),
          child: Icon(
            icon,
            size: 18,
            color: selected ? color : const Color(0xFFD4D4D8),
          ),
        ),
      ),
    );
  }
}

class _TrackListTile extends StatelessWidget {
  const _TrackListTile({required this.track, required this.color});

  final TrackRecommendation track;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF171721),
        borderRadius: BorderRadius.circular(12),
      ),
      child: ListTile(
        leading: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: SizedBox(
            width: 46,
            height: 46,
            child: _TrackArt(url: track.albumArtUrl, color: color),
          ),
        ),
        title: Text(track.name, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          track.artist,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
    );
  }
}

class _TrackArt extends StatelessWidget {
  const _TrackArt({required this.url, required this.color});

  final String? url;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final imageUrl = url ?? '';
    if (imageUrl.isNotEmpty) {
      return Image.network(
        imageUrl,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => _fallback(),
      );
    }
    return _fallback();
  }

  Widget _fallback() {
    return Container(
      color: const Color(0xFF1D1D27),
      alignment: Alignment.center,
      child: Icon(
        Icons.music_note_rounded,
        color: color.withValues(alpha: 0.86),
      ),
    );
  }
}
