import 'package:flutter/material.dart';

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.keyword});

  final String keyword;

  @override
  Widget build(BuildContext context) {
    const groups = [
      _NodeData('의외로 낮은 유사도', 0.22, Offset(0.18, 0.20), Color(0xFFF472B6)),
      _NodeData('개인 맞춤형 추천', 0.79, Offset(0.84, 0.34), Color(0xFF2DD4BF)),
      _NodeData('기타 탐색', 0.56, Offset(0.72, 0.78), Color(0xFF64748B)),
      _NodeData('소수 취향 확장', 0.68, Offset(0.28, 0.78), Color(0xFF60A5FA)),
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
                              child: _MainTrackCard(keyword: keyword),
                            ),
                            ...groups.map((node) {
                              return Positioned(
                                left: constraints.maxWidth * node.anchor.dx - 56,
                                top: constraints.maxHeight * node.anchor.dy - 42,
                                child: _GroupNode(node: node),
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
}

class _MainTrackCard extends StatelessWidget {
  const _MainTrackCard({required this.keyword});

  final String keyword;

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
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              gradient: const LinearGradient(colors: [Color(0xFF111827), Color(0xFF4B5563)]),
            ),
            alignment: Alignment.center,
            child: const Icon(Icons.music_note_rounded, size: 48, color: Colors.white),
          ),
          const SizedBox(height: 12),
          const Text('Night Transit', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text('for "$keyword"', style: const TextStyle(color: Color(0xFFA1A1AA), fontSize: 12)),
          const SizedBox(height: 8),
          const Text('유사도 91%', style: TextStyle(color: Color(0xFF2DD4BF), fontWeight: FontWeight.w600)),
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
}

class _GroupNode extends StatelessWidget {
  const _GroupNode({required this.node});

  final _NodeData node;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 112,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF15151D).withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: node.color.withValues(alpha: 0.68)),
        boxShadow: [
          BoxShadow(color: node.color.withValues(alpha: 0.16), blurRadius: 14, offset: const Offset(0, 6)),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.album_rounded, size: 24, color: node.color),
          const SizedBox(height: 6),
          Text(
            node.label,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            '연관도 ${(node.score * 100).round()}%',
            style: const TextStyle(fontSize: 11, color: Color(0xFFA1A1AA)),
          ),
        ],
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
      final paint = Paint()
        ..color = node.color.withValues(alpha: 0.45)
        ..strokeWidth = 1.4 + (node.score * 2.4)
        ..style = PaintingStyle.stroke;
      canvas.drawLine(center, end, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _GraphEdgePainter oldDelegate) {
    return oldDelegate.center != center || oldDelegate.nodes != nodes;
  }
}

class _NodeData {
  const _NodeData(this.label, this.score, this.anchor, this.color);

  final String label;
  final double score;
  final Offset anchor;
  final Color color;
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
