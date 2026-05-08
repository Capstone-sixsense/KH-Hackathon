import 'package:flutter/material.dart';
import 'package:khuthon/screens/search_screen.dart';

void main() {
  runApp(const SideBApp());
}

class SideBApp extends StatelessWidget {
  const SideBApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Side-B',
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFF0B0B0F),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF4B5563),
          brightness: Brightness.dark,
        ),
        fontFamily: 'Nunito',
      ),
      home: const SearchScreen(),
    );
  }
}
