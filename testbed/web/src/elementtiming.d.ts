import "react";

declare module "react" {
  interface HTMLAttributes<T> {
    elementtiming?: string;
  }
}
