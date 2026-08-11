type SnakeToCamelCase<S extends string> = S extends `${infer T}_${infer U}`
  ? `${T}${Capitalize<SnakeToCamelCase<U>>}`
  : S;

type CamelToSnakeCase<S extends string> = S extends `${infer T}${infer U}`
  ? `${T extends Capitalize<T>
      ? '_'
      : ''}${Lowercase<T>}${CamelToSnakeCase<U>}`
  : S;

type TransformObject<T> = {
  [K in keyof T as SnakeToCamelCase<K & string>]: T[K] extends object
    ? TransformObject<T[K]>
    : T[K];
};

type TransformToSnakeCase<T> = {
  [K in keyof T as CamelToSnakeCase<K & string>]: T[K] extends object
    ? TransformToSnakeCase<T[K]>
    : T[K];
};

export function transformToCamelCase<T>(obj: T): TransformObject<T> {
  if (Array.isArray(obj)) {
    return obj.map(transformToCamelCase) as TransformObject<T>;
  }

  if (obj !== null && typeof obj === 'object') {
    return Object.entries(obj).reduce((acc, [key, value]) => {
      const camelKey = key.replace(/_([a-z])/g, (_, letter) =>
        letter.toUpperCase()
      );
      return {
        ...acc,
        [camelKey]: transformToCamelCase(value),
      };
    }, {} as TransformObject<T>);
  }

  return obj as TransformObject<T>;
}

export function transformToSnakeCase<T>(obj: T): TransformToSnakeCase<T> {
  if (Array.isArray(obj)) {
    return obj.map(transformToSnakeCase) as TransformToSnakeCase<T>;
  }

  if (obj !== null && typeof obj === 'object') {
    return Object.entries(obj).reduce((acc, [key, value]) => {
      const snakeKey = key.replace(
        /[A-Z]/g,
        (letter) => `_${letter.toLowerCase()}`
      );
      return {
        ...acc,
        [snakeKey]: transformToSnakeCase(value),
      };
    }, {} as TransformToSnakeCase<T>);
  }

  return obj as TransformToSnakeCase<T>;
} 