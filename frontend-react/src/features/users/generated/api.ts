// Generated from the backend OpenAPI dependency closure; run pnpm generate:contracts.
export type paths = Record<string, never>;
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** UserPublic */
        UserPublic: {
            /** Username */
            username: string;
            /** @default admin */
            role: components["schemas"]["UserRole"];
            /** Id */
            id: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /**
         * UserRole
         * @enum {string}
         */
        UserRole: "admin" | "owner";
        /** UserCreate */
        UserCreate: {
            /** Username */
            username: string;
            /** Password */
            password: string;
            /** @default admin */
            role: components["schemas"]["UserRole"];
        };
        /** LoginResponse */
        LoginResponse: {
            user: components["schemas"]["UserPublic"];
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export type operations = Record<string, never>;
