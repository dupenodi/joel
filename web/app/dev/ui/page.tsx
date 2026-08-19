import { notFound } from "next/navigation";
import { DesignLanguageGallery } from "./gallery-client";

/**
 * Single design-language page: tokens, atoms, then the company-brain kit.
 * Gated out of production so mock catalog data cannot ship.
 */
export default function UiGalleryPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }
  return <DesignLanguageGallery />;
}
