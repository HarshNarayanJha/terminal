// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

#include "precomp.h"
#include "WexTestClass.h"

#include "../types/inc/CodepointWidthDetector.hpp"

class CodepointWidthDetectorTests
{
    TEST_CLASS(CodepointWidthDetectorTests);

    TEST_METHOD(Graphemes)
    {
        static constexpr std::wstring_view text{ L"a\u0363e\u0364\u0364i\u0365" };

        auto& cwd = CodepointWidthDetector::Singleton();

        const std::vector<size_t> expectedAdvances{ 2, 3, 2 };
        const std::vector<int> expectedWidths{ 1, 1, 1 };
        std::vector<size_t> actualAdvances;
        std::vector<int> actualWidths;

        for (size_t beg = 0; beg < text.size();)
        {
            int width;
            const auto end = cwd.GraphemeNext(text, beg, &width);
            actualAdvances.emplace_back(end - beg);
            actualWidths.emplace_back(width);
            beg = end;
        }

        VERIFY_ARE_EQUAL(expectedAdvances, actualAdvances);
        VERIFY_ARE_EQUAL(expectedWidths, actualWidths);

        actualAdvances.clear();
        actualWidths.clear();

        for (size_t end = text.size(); end > 0;)
        {
            int width;
            const auto beg = cwd.GraphemePrev(text, end, &width);
            actualAdvances.emplace_back(end - beg);
            actualWidths.emplace_back(width);
            end = beg;
        }

        std::reverse(actualAdvances.begin(), actualAdvances.end());
        std::reverse(actualWidths.begin(), actualWidths.end());

        VERIFY_ARE_EQUAL(expectedAdvances, actualAdvances);
        VERIFY_ARE_EQUAL(expectedWidths, actualWidths);
    }
};
