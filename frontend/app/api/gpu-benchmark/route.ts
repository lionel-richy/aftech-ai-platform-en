import { NextResponse } from "next/server";

import { lireComparisonGpu } from "@/lib/gpuBenchmark";

export async function GET() {
  const comparaison = await lireComparisonGpu();
  return NextResponse.json(comparaison);
}
