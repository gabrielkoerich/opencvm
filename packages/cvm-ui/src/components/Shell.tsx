import { type ParentComponent } from "solid-js";
import { TopBar } from "./TopBar";

export const Shell: ParentComponent = (props) => (
  <div class="scanlines flex h-full w-full flex-col bg-bg text-text">
    <TopBar />
    <main class="relative flex-1 overflow-auto">
      <div class="fade-in h-full">{props.children}</div>
    </main>
  </div>
);
