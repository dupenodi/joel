import { notFound } from "next/navigation";
import { UiGalleryClient } from "./ui-gallery-client";

/**
 * Component preview gallery — the single place mock/sample data is allowed to
 * live in this app. Gated out of production builds so it can never be
 * reached (or mistaken for real product data) in a deployed environment.
 */
export default function UiGalleryPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }
  return <UiGalleryClient />;
}
