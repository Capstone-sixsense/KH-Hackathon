import 'package:flutter/material.dart';
import 'package:khuthon/models/recommendation_models.dart';

enum _TrackViewMode { gallery, list }

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.keyword, required this.response});

  final String keyword;
  final RecommendResponse response;

  @override
  Widget build(BuildContext context) {
    final allTracks = <TrackRecommendation>[
      ...response.similar,
      ...response.reverse,
      ...response.opposite,
    ];
    final mainTrack = allTracks.isNotEmpty
        ? (allTracks..sort((a, b) => (b.reverseScore ?? 0).compareTo(a.reverseScore ?? 0))).first
        : null;
    final groups = [
      _NodeData(
        label: '의외로 낮은 유사도',
        description: '반대 감성 기반 추천',
        score: response.reverse.length.toDouble(),
        anchor: const Offset(0.18, 0.20),
        color: const Color(0xFFD38FB4),
        tracks: response.reverse,
      ),
      _NodeData(
        label: '개인 맞춤형 추천',
        description: '비슷한 청취 패턴 추천',
        score: response.similar.length.toDouble(),
        anchor: const Offset(0.84, 0.34),
        color: const Color(0xFF7CBFB3),
        tracks: response.similar,
      ),
      _NodeData(
        label: '기타 탐색',
        description: '감성 반대편 탐색',
        score: response.opposite.length.toDouble(),
        anchor: const Offset(0.72, 0.78),
        color: const Color(0xFF8A95A6),
        tracks: response.opposite,
      ),
      _NodeData(
        label: '소수 취향 확장',
        description: '전체 풀 확장 탐색',
        score: allTracks.length.toDouble(),
        anchor: const Offset(0.28, 0.78),
        color: const Color(0xFF83A8D6),
        tracks: allTracks,
      ),
    ];

    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            Positioned(
              right: -120,
              top: -80,
              child: _GlowOrb(size: 280, color: const Color(0xFF2DD4BF).withValues(alpha: 0.11)),
            ),
            Positioned(
              left: -140,
              bottom: -120,
              child: _GlowOrb(size: 340, color: const Color(0xFF374151).withValues(alpha: 0.14)),
            ),
            Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      IconButton(
                        onPressed: () => Navigator.of(context).pop(),
                        icon: const Icon(Icons.arrow_back_ios_new_rounded),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '"$keyword" 탐색 결과',
                          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Expanded(
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final center = Offset(constraints.maxWidth * 0.5, constraints.maxHeight * 0.46);
                        return Stack(
                          children: [
                            CustomPaint(
                              size: Size(constraints.maxWidth, constraints.maxHeight),
                              painter: _GraphEdgePainter(center: center, nodes: groups),
                            ),
                            Align(
                              alignment: const Alignment(0, -0.1),
                              child: _MainTrackCard(keyword: keyword, track: mainTrack),
                            ),
                            ...groups.map((node) {
                              return Positioned(
                                left: constraints.maxWidth * node.anchor.dx - 74,
                                top: constraints.maxHeight * node.anchor.dy - 62,
                                child: _GroupNode(
                                  node: node,
                                  onTap: () => _openGroupTracks(context, node),
                                ),
                              );
                            }),
                          ],
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
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
  const _MainTrackCard({required this.keyword, required this.track});

  final String keyword;
  final TrackRecommendation? track;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 245,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF1A1A25), Color(0xFF12121A)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
        boxShadow: const [BoxShadow(color: Color(0x55000000), blurRadius: 24, offset: Offset(0, 10))],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if ((track?.albumArtUrl ?? '').isNotEmpty)
            ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: Image.network(
                track!.albumArtUrl!,
                width: 120,
                height: 120,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => _fallbackArt(),
              ),
            )
          else
            _fallbackArt(),
          const SizedBox(height: 12),
          Text(track?.name ?? 'No Result', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(
            track == null ? 'for "$keyword"' : '${track!.artist} · "$keyword"',
            style: const TextStyle(color: Color(0xFFA1A1AA), fontSize: 12),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: () {},
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF0F766E),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
              child: const Text('Spotify에서 듣기'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _fallbackArt() {
    return Container(
      width: 120,
      height: 120,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        gradient: const LinearGradient(colors: [Color(0xFF111827), Color(0xFF4B5563)]),
      ),
      alignment: Alignment.center,
      child: const Icon(Icons.music_note_rounded, size: 48, color: Colors.white),
    );
  }
}

class _GroupNode extends StatefulWidget {
  const _GroupNode({required this.node, required this.onTap});

  final _NodeData node;
  final VoidCallback onTap;

  @override
  State<_GroupNode> createState() => _GroupNodeState();
}

class _GroupNodeState extends State<_GroupNode> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final galleryTracks = widget.node.tracks.take(4).toList();
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedScale(
          scale: _hovered ? 1.06 : 1.0,
          duration: const Duration(milliseconds: 170),
          curve: Curves.easeOut,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 170),
            width: 148,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFF15151D).withValues(alpha: 0.9),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: widget.node.color.withValues(alpha: _hovered ? 0.95 : 0.68)),
              boxShadow: [
                BoxShadow(
                  color: widget.node.color.withValues(alpha: _hovered ? 0.28 : 0.16),
                  blurRadius: _hovered ? 18 : 14,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 128,
                  height: 84,
                  child: Column(
                    children: [
                      Row(
                        children: [
                          Expanded(child: _AlbumThumb(track: galleryTracks.isNotEmpty ? galleryTracks[0] : null, color: widget.node.color)),
                          const SizedBox(width: 4),
                          Expanded(child: _AlbumThumb(track: galleryTracks.length > 1 ? galleryTracks[1] : null, color: widget.node.color)),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Expanded(child: _AlbumThumb(track: galleryTracks.length > 2 ? galleryTracks[2] : null, color: widget.node.color)),
                          const SizedBox(width: 4),
                          Expanded(child: _AlbumThumb(track: galleryTracks.length > 3 ? galleryTracks[3] : null, color: widget.node.color)),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  widget.node.label,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 3),
                Text(
                  widget.node.description,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 10, color: Color(0xFFA1A1AA)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _GraphEdgePainter extends CustomPainter {
  _GraphEdgePainter({required this.center, required this.nodes});

  final Offset center;
  final List<_NodeData> nodes;

  @override
  void paint(Canvas canvas, Size size) {
    for (final node in nodes) {
      final end = Offset(size.width * node.anchor.dx, size.height * node.anchor.dy);
      final isLeft = end.dx < center.dx;
      final control = Offset(
        (center.dx + end.dx) / 2 + (isLeft ? -34 : 34),
        (center.dy + end.dy) / 2 - 24,
      );
      final path = Path()
        ..moveTo(center.dx, center.dy)
        ..quadraticBezierTo(control.dx, control.dy, end.dx, end.dy);
      final paint = Paint()
        ..color = node.color.withValues(alpha: 0.24)
        ..strokeWidth = 0.8 + (node.score * 1.5)
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round;
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _GraphEdgePainter oldDelegate) {
    return oldDelegate.center != center || oldDelegate.nodes != nodes;
  }
}

class _NodeData {
  const _NodeData({
    required this.label,
    required this.description,
    required this.score,
    required this.anchor,
    required this.color,
    required this.tracks,
  });

  final String label;
  final String description;
  final double score;
  final Offset anchor;
  final Color color;
  final List<TrackRecommendation> tracks;
}

class _AlbumThumb extends StatelessWidget {
  const _AlbumThumb({required this.track, required this.color});

  final TrackRecommendation? track;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final url = track?.albumArtUrl ?? '';
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Container(
        width: double.infinity,
        height: 40,
        color: const Color(0xFF1D1D27),
        child: url.isNotEmpty
            ? Image.network(
                url,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => _fallback(),
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

class _GlowOrb extends StatelessWidget {
  const _GlowOrb({required this.size, required this.color});

  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, color.withValues(alpha: 0)],
            stops: const [0.15, 1],
          ),
        ),
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
                border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _ViewModeToggleChip(
                    icon: Icons.grid_view_rounded,
                    tooltip: '갤러리',
                    selected: _mode == _TrackViewMode.gallery,
                    color: widget.color,
                    onTap: () => setState(() => _mode = _TrackViewMode.gallery),
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
                    child: Text('표시할 추천 곡이 없습니다.', style: TextStyle(color: Color(0xFFA1A1AA))),
                  )
                : _mode == _TrackViewMode.gallery
                    ? GridView.builder(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 6,
                          mainAxisSpacing: 10,
                          crossAxisSpacing: 10,
                          childAspectRatio: 0.85,
                        ),
                        itemCount: widget.tracks.length,
                        itemBuilder: (context, index) {
                          final track = widget.tracks[index];
                          return _TrackGalleryCard(track: track, color: widget.color);
                        },
                      )
                    : ListView.separated(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                        itemCount: widget.tracks.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (context, index) {
                          final track = widget.tracks[index];
                          return _TrackListTile(track: track, color: widget.color);
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
          Text(track.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text(track.artist, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 10, color: Color(0xFFA1A1AA))),
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
            color: selected ? color.withValues(alpha: 0.22) : Colors.transparent,
            border: Border.all(
              color: selected ? color.withValues(alpha: 0.72) : Colors.white.withValues(alpha: 0.1),
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
        subtitle: Text(track.artist, maxLines: 1, overflow: TextOverflow.ellipsis),
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
        errorBuilder: (_, __, ___) => _fallback(),
      );
    }
    return _fallback();
  }

  Widget _fallback() {
    return Container(
      color: const Color(0xFF1D1D27),
      alignment: Alignment.center,
      child: Icon(Icons.music_note_rounded, color: color.withValues(alpha: 0.86)),
    );
  }
}
